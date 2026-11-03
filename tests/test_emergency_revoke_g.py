"""g · Revocación de emergencia visible en la demo, sobre el endpoint real del gateway."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from shield.gateway.app import create_app
from shield.registry import Registry
from shield.vault.vault import MemoryVault
from tests.test_live_h14 import make_chain
from web.app import create_panel_app
from web.emergency import run_emergency_revoke
from web.replay_run import ReplayRun


def _gateway(key: str | None, upstream_calls: list):
    reg = Registry(":memory:")

    def _upstream(request: httpx.Request) -> httpx.Response:
        upstream_calls.append(request)
        return httpx.Response(200, json={})

    app = create_app(
        registry=reg,
        vault=MemoryVault({}),
        upstream_transport=httpx.MockTransport(_upstream),
        sandbox=True,
        emergency_token=key,
    )
    return reg, app


def test_gateway_emergency_token_per_instance(monkeypatch):
    monkeypatch.delenv("SHIELD_EMERGENCY_TOKEN", raising=False)
    calls: list = []
    reg, app = _gateway(None, calls)
    with TestClient(app) as c:
        assert c.post("/shield/revoke-all").status_code == 503
    reg, app = _gateway("k-123", calls)
    reg.create_token("bodega", "crew", models=["muse-spark-1.3"])
    with TestClient(app) as c:
        bad = c.post("/shield/revoke-all", headers={"x-shield-emergency": "bad"})
        assert bad.status_code == 401
        ok = c.post("/shield/revoke-all", headers={"x-shield-emergency": "k-123"})
        assert ok.status_code == 200 and ok.json() == {"revoked": 1}


def test_probe_never_reaches_upstream_and_skips_active_tokens():
    calls: list = []
    reg, app = _gateway("k", calls)
    _tok, raw = reg.create_token("bodega", "crew", models=["muse-spark-1.3"])
    with TestClient(app) as c:
        # Llave mala: no revoca, no prueba nada.
        bad = run_emergency_revoke(c, "wrong", [("bodega", raw)], registry=reg)
        assert bad["status"] == "error" and bad["http_status"] == 401
        out = run_emergency_revoke(c, "k", [("bodega", raw), ("dup", raw)], registry=reg)
    assert out["status"] == "ok" and out["revoked"] == 1 and out["all_locked"]
    assert out["probes"] == [{"agent": "bodega", "status": 401, "code": "revoked_token"}]
    assert calls == []


def test_live_chain_revoke_locks_every_token_without_model_calls():
    chain, handler = make_chain()
    try:
        chain.step_count()
        chain.step_attack()
        before = len(handler.calls)
        cost = chain.total_cost_usd
        out = chain.step_revoke()
        assert out["status"] == "ok", out
        assert out["revoked"] >= 3
        assert {p["agent"] for p in out["probes"]} >= {"attacker", "compras", "guardian"}
        assert all(p["status"] == 401 for p in out["probes"])
        assert len(handler.calls) == before and chain.total_cost_usd == cost
        dumped = json.dumps(chain.state())
        assert chain._emergency_token not in dumped
        assert chain.state()["results"]["revoke"]["all_locked"] is True
    finally:
        chain.close()


@pytest.mark.parametrize("scene", ["bodega", "frio"])
def test_replay_revoke_is_real_and_needs_attack(scene):
    run = ReplayRun(scene)
    assert run.step("revoke")["status"] == "error"
    for step in ("invoice", "count", "attack"):
        run.step(step)
    out = run.step("revoke")
    assert out["status"] == "ok", out
    assert out["revoked"] == 3 and out["all_locked"]
    assert [p["agent"] for p in out["probes"]][0] == "attacker"


def test_replay_revoke_after_contain_reports_rotated_attacker():
    run = ReplayRun("bodega")
    for step in ("invoice", "count", "attack", "guardian"):
        run.step(step)
    assert run.voice("sí, rota el token de bodega")["status"] == "approved"
    run.step("contain")
    out = run.step("revoke")
    assert out["status"] == "ok"
    codes = {p["agent"]: p["code"] for p in out["probes"]}
    assert codes["attacker"] == "rotated_token" and codes["compras"] == "revoked_token"


def test_public_replay_endpoint_and_button(monkeypatch):
    monkeypatch.setenv("DEMO", "replay")
    monkeypatch.setenv("SHIELD_PANEL_SESSIONS", "1")
    monkeypatch.setenv("SHIELD_REPLAY_HOME", "1")
    c = TestClient(create_panel_app())
    page = c.get("/?lang=es").text
    assert "data-run-step='revoke'" in page and "Emergencia: revocar todos los tokens" in page
    assert "Emergency: revoke every token" in c.get("/?lang=en").text
    for step in ("invoice", "count", "attack"):
        assert c.post(f"/replay/step/{step}").status_code == 200
    r = c.post("/replay/step/revoke")
    assert r.status_code == 200 and r.json()["all_locked"] is True
    assert c.get("/replay/state").json()["results"]["revoke"]["revoked"] == 3
    assert c.post("/live/step/revoke").status_code == 403
