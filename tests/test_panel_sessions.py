"""Demo pública: una corrida de replay por visitante (SHIELD_PANEL_SESSIONS=1)."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from web.app import SessionStore, create_panel_app


@pytest.fixture
def public_app(monkeypatch):
    monkeypatch.setenv("SHIELD_PANEL_SESSIONS", "1")
    monkeypatch.setenv("DEMO", "replay")
    return create_panel_app()


def _approval_id(html: str) -> str:
    m = re.search(r"/panel/approve/([^'\"]+)", html)
    assert m, "no hay aprobación pendiente"
    return m.group(1)


def test_each_visitor_gets_own_run(public_app):
    a, b = TestClient(public_app), TestClient(public_app)
    page_a = a.get("/")
    assert page_a.status_code == 200
    assert "panel_sid" in page_a.headers.get("set-cookie", "")
    assert "HttpOnly" in page_a.headers["set-cookie"]
    a.post("/panel/approve/" + _approval_id(page_a.text), headers={"X-Panel-Fetch": "1"})
    # A contuvo el incidente; B sigue viendo el suyo intacto.
    assert a.get("/panel/state").json()["phase"] == "contained"
    page_b = b.get("/")
    assert b.get("/panel/state").json()["phase"] == "pending"
    assert "/panel/approve/" in page_b.text


def test_reset_only_affects_own_session(public_app):
    a, b = TestClient(public_app), TestClient(public_app)
    page_a = a.get("/")
    b.get("/")
    b.post("/panel/approve/" + _approval_id(b.get("/").text), headers={"X-Panel-Fetch": "1"})
    a.post("/panel/approve/" + _approval_id(page_a.text), headers={"X-Panel-Fetch": "1"})
    reset = a.post("/panel/reset", headers={"X-Panel-Fetch": "1"})
    assert reset.status_code == 200
    assert a.get("/panel/state").json()["phase"] == "pending"
    assert b.get("/panel/state").json()["phase"] == "contained"


def test_full_chain_in_session_is_replay_without_network(public_app):
    c = TestClient(public_app)
    page = c.get("/")
    assert "Replay" in page.text
    c.post("/panel/approve/" + _approval_id(page.text), headers={"X-Panel-Fetch": "1"})
    state = c.get("/panel/state").json()
    assert state["demo"] == "replay"
    assert state["phase"] == "contained"
    assert state["attacker_statuses"][0] == 200 and state["attacker_statuses"][-1] == 401
    assert state["agent_statuses"]["bodega"][-1] == 200
    assert state["agent_statuses"]["compras"][-1] == 200
    rotated = [e for e in state["executed"] if e["action"] == "rotate_token"]
    assert [e["target"] for e in rotated if e["status"] == "applied"] == ["bodega"]


def test_public_mode_has_no_live_docs_or_whatsapp(public_app):
    c = TestClient(public_app)
    assert c.get("/docs").status_code == 404
    assert c.get("/openapi.json").status_code == 404
    assert c.get("/webhook/whatsapp").status_code in (404, 405)
    assert c.post("/webhook/whatsapp", json={}).status_code in (404, 405)
    assert c.post("/live/start").status_code == 403
    assert c.post("/live/step/attack").status_code == 403
    live = c.get("/live")
    assert live.status_code == 200
    assert c.get("/health").text == "ok"


def test_session_store_caps_and_expires():
    store = SessionStore(max_sessions=2, ttl_s=1000)
    s1, _, _ = store.get_or_create(None)
    store.get_or_create(None)
    store.get_or_create(None)
    assert len(store) == 2
    # la más vieja salió; su cookie recibe una corrida nueva sin error
    again, _, created = store.get_or_create(s1)
    assert created and again != s1
    short = SessionStore(max_sessions=5, ttl_s=0)
    sid, _, _ = short.get_or_create(None)
    _, _, created = short.get_or_create(sid)
    assert created


def test_new_run_clears_previous_run_before_reload():
    from web.live_page import render_live_page

    html = render_live_page("en")
    handler = html.split('byId("newRunBtn").addEventListener')[1][:300]
    assert handler.index("/reset") < handler.index("clearRun()") < handler.index("reload")
    body = html.split("function clearRun()")[1].split("document.addEventListener")[0]
    for node in ("voiceTranscript", "voiceIntent", "attackerAfter", "containedLine", "typedText"):
        assert node in body
