"""Repetición pública: carrera reset/paso, contención cerrada, relojes y HEAD /."""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from web.app import create_panel_app


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DEMO", "replay")
    monkeypatch.setenv("SHIELD_PANEL_SESSIONS", "1")
    monkeypatch.setenv("SHIELD_REPLAY_HOME", "1")
    return TestClient(create_panel_app())


def _run_until_owner(c: TestClient) -> None:
    for step in ("invoice", "count", "attack", "guardian"):
        r = c.post(f"/replay/step/{step}")
        assert r.status_code == 200, (step, r.text)


def _contain(c: TestClient) -> dict:
    _run_until_owner(c)
    ok = c.post("/replay/voice", data={"typed": "sí, rota el token de bodega"}).json()
    assert ok["status"] == "approved"
    r = c.post("/replay/step/contain")
    assert r.status_code == 200, r.text
    return r.json()


def test_reset_during_step_discards_the_step_as_stale(client):
    client.get("/")
    old = client.get("/replay/state").json()["run_id"]
    out: dict = {}

    def _step() -> None:
        r = client.post("/replay/step/invoice")
        out["code"], out["body"] = r.status_code, r.json()

    t = threading.Thread(target=_step)
    t.start()
    time.sleep(0.15)  # el paso duerme 0,6 s antes de correr: «New run» llega en medio
    fresh = client.post("/replay/reset").json()
    t.join()
    assert fresh["run_id"] != old
    assert out["code"] == 409
    assert out["body"]["status"] == "stale"
    state = client.get("/replay/state").json()
    assert state["run_id"] == fresh["run_id"]
    assert state["results"] == {}  # la corrida nueva no hereda la factura vieja
    assert state["provenance"] == []


def test_attack_and_guardian_rejected_after_contain(client):
    client.get("/")
    _contain(client)
    approval = client.get("/replay/state").json()["approval_id"]
    for step in ("attack", "guardian"):
        r = client.post(f"/replay/step/{step}")
        assert r.status_code == 409
        assert "start a new run" in r.json()["error"]
    state = client.get("/replay/state").json()
    assert state["approval_id"] == approval  # no se creó otra aprobación
    assert state["voice"]["status"] == "approved"
    # La corrida nueva vuelve a permitir el ataque.
    client.post("/replay/reset")
    _run_until_owner(client)


def test_bodega_time_to_401_is_the_visitor_s_and_recorded_shown_apart(client):
    client.get("/")
    done = _contain(client)
    # Medido desde attack_started_at del visitante: segundos de la prueba, no los 47 s grabados.
    assert done["contained_in_s"] < 30
    assert done["recorded_contained_in_s"] == pytest.approx(47.021)
    state = client.get("/replay/state").json()
    assert state["contained_in_s"] == done["contained_in_s"]


def test_chain_duration_does_not_run_before_first_step(client):
    client.get("/")
    time.sleep(0.05)
    before = client.get("/replay/state").json()
    assert before["duration_s"] == 0
    assert before["started_at"] is None
    client.post("/replay/step/invoice")
    after = client.get("/replay/state").json()
    assert after["started_at"] is not None
    client.post("/replay/reset")
    assert client.get("/replay/state").json()["duration_s"] == 0


def test_head_root_answers_200(client):
    r = client.head("/")
    assert r.status_code == 200


def test_page_js_aborts_on_new_run_and_restores_step_states():
    from web.live_page import render_live_page

    html = render_live_page("en", replay=True)
    new_run = html.split('byId("newRunBtn").addEventListener')[1][:400]
    assert "runCtl.abort()" in new_run
    assert new_run.index("runCtl.abort()") < new_run.index('"/reset"')
    step = html.split("async function runStep(step)")[1][:1800]
    assert 'data.status === "stale"' in step
    clear_run = html.split("function clearRun()")[1][:1200]
    for box in ("invoiceResult", "countResult", "guardianResult"):
        assert box in clear_run
    until = html.split("async function runUntilOwner()")[1][:700]
    assert "focusApproval()" in until
    assert "done.guardian || done.contain" in until
    # Al recargar: los pasos con resultado pasan a ok (no «not run»).
    band = html.split("function updateBand(state)")[1].split("async function refreshState()")[0]
    assert "stopStatus(step, TEXT.ok)" in band
    assert "recorded_live_run" in html and "toFixed(1)" in html
