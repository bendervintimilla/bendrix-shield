"""C2490: modo en vivo publicado (código de acceso + tope diario). Sin red real."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.test_live_h14 import make_chain
from web.app import create_panel_app
from web.live_access import (
    AccessGate,
    MemoryStore,
    SpendLedger,
    make_ticket,
    remote_enabled,
)

CODE = "test-access-code-0123456789abcdef"


class _FailingStore:
    def load(self):
        raise OSError("gcs down")

    def save(self, data):  # pragma: no cover
        raise OSError("gcs down")


@pytest.fixture
def remote_env(monkeypatch):
    monkeypatch.setenv("DEMO", "live")
    monkeypatch.setenv("SHIELD_LIVE_REMOTE", "1")
    monkeypatch.setenv("LIVE_ACCESS_CODE", CODE)
    monkeypatch.delenv("SHIELD_PANEL_SESSIONS", raising=False)
    monkeypatch.delenv("SHIELD_LEDGER_GCS", raising=False)


def _login(client: TestClient) -> None:
    r = client.post("/live/login", data={"code": CODE}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/live"


def test_remote_disabled_by_default_and_short_code(monkeypatch):
    monkeypatch.delenv("SHIELD_LIVE_REMOTE", raising=False)
    monkeypatch.setenv("LIVE_ACCESS_CODE", CODE)
    assert not remote_enabled()
    monkeypatch.setenv("SHIELD_LIVE_REMOTE", "1")
    assert remote_enabled()
    monkeypatch.setenv("LIVE_ACCESS_CODE", "corto")
    assert not remote_enabled()


def test_requires_code_for_everything_live(remote_env):
    chain, _h = make_chain()
    try:
        client = TestClient(create_panel_app(live_chain=chain), client=("203.0.113.9", 1))
        page = client.get("/live", follow_redirects=False)
        assert page.status_code == 303 and page.headers["location"] == "/live/login"
        for method, path in [
            ("post", "/live/start"),
            ("post", "/live/step/invoice"),
            ("post", "/live/voice"),
            ("get", "/live/state"),
            ("get", "/live/budget"),
            ("get", "/live/provenance.json"),
        ]:
            assert getattr(client, method)(path).status_code == 401, path
        assert client.get("/", follow_redirects=False).headers["location"] == "/live"
        assert client.get("/docs").status_code == 404
        assert client.post("/webhook/whatsapp").status_code in (404, 405)
        assert "Access code" in client.get("/live/login").text
    finally:
        chain.close()


def test_wrong_code_then_lockout_then_ok(remote_env):
    chain, _h = make_chain()
    try:
        client = TestClient(create_panel_app(live_chain=chain))
        for _ in range(4):
            assert client.post("/live/login", data={"code": "mal"}).status_code == 401
        assert client.post("/live/login", data={"code": "mal"}).status_code == 429
        # Bloqueado: ni el código correcto entra mientras dura el bloqueo.
        assert client.post("/live/login", data={"code": CODE}).status_code == 429
        assert "live_auth" not in client.cookies
    finally:
        chain.close()


def test_login_sets_strict_httponly_cookie_and_allows_flow(remote_env):
    chain, _h = make_chain()
    try:
        client = TestClient(
            create_panel_app(live_chain=chain),
            base_url="https://testserver",
            client=("203.0.113.9", 1),
        )
        r = client.post(
            "/live/login",
            data={"code": CODE},
            headers={"x-forwarded-proto": "https"},
            follow_redirects=False,
        )
        cookie = r.headers["set-cookie"]
        assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
        assert CODE not in cookie
        assert client.get("/live").status_code == 200
        assert client.post("/live/start").status_code == 200
        assert client.post("/live/step/count").json()["count"] == 7
        # CSRF: un origen distinto al host se rechaza aunque haya cookie.
        evil = client.post("/live/step/count", headers={"origin": "https://evil.example"})
        assert evil.status_code == 403
        budget = client.get("/live/budget").json()
        assert budget["max_usd"] == 5 and budget["max_runs"] == 20
        assert budget["runs"] == 1 and budget["ledger_ok"] is True
        assert client.post("/live/logout", follow_redirects=False).status_code == 303
    finally:
        chain.close()


def test_ticket_logs_in_once_valid_and_expires(remote_env):
    chain, _h = make_chain()
    try:
        client = TestClient(create_panel_app(live_chain=chain))
        r = client.get(f"/live/login?t={make_ticket(CODE)}", follow_redirects=False)
        assert r.status_code == 303 and "live_auth" in r.headers["set-cookie"]
        old = make_ticket(CODE, ttl_s=1, now=1000)
        other = TestClient(create_panel_app(live_chain=chain))
        assert "Access code" in other.get(f"/live/login?t={old}").text
        forged = make_ticket("otro-codigo-distinto-123456", ttl_s=600)
        assert "Access code" in other.get(f"/live/login?t={forged}").text
    finally:
        chain.close()


def test_gate_cookie_expiry_and_tamper():
    gate = AccessGate(CODE)
    cookie = gate.make_cookie(now=1000)
    assert gate.cookie_ok(cookie, now=1001)
    assert not gate.cookie_ok(cookie, now=1000 + 13 * 3600)
    exp, mac = cookie.split(".")
    assert not gate.cookie_ok(f"{int(exp) + 99999}.{mac}", now=1001)
    assert not gate.cookie_ok("basura", now=1001)


def test_daily_runs_cap_blocks_without_calling_model(remote_env, monkeypatch):
    chain, handler = make_chain()
    try:
        app = create_panel_app(live_chain=chain)
        app.state.live_ledger.max_runs = 1
        client = TestClient(app)
        _login(client)
        client.post("/live/start")
        assert client.post("/live/step/invoice").status_code == 200
        # Misma corrida: sigue permitido (no es una corrida nueva).
        assert client.post("/live/step/attack").status_code == 200
        client.post("/live/reset")
        before = handler.calls["n"]
        blocked = client.post("/live/step/invoice")
        assert blocked.status_code == 429
        body = blocked.json()
        assert body["error"] == "daily_limit" and "Daily limit reached" in body["message"]
        assert handler.calls["n"] == before  # el modelo NO se llamó
    finally:
        chain.close()


def test_daily_usd_cap_blocks_without_calling_model(remote_env):
    chain, handler = make_chain()
    try:
        app = create_panel_app(live_chain=chain)
        ledger: SpendLedger = app.state.live_ledger
        ledger.max_usd = 0.05  # menor que la reserva por paso
        client = TestClient(app)
        _login(client)
        client.post("/live/start")
        before = handler.calls["n"]
        blocked = client.post("/live/step/guardian")
        assert blocked.status_code == 429
        assert "spend limit" in blocked.json()["message"]
        assert handler.calls["n"] == before
    finally:
        chain.close()


def test_ledger_records_cost_per_run_and_resets_next_day(capsys):
    store = MemoryStore()
    day = {"d": "2026-11-03"}
    ledger = SpendLedger(store, max_usd=5, max_runs=20, today=lambda: day["d"])
    assert ledger.allow("live_a") == (True, "")
    line = ledger.record("live_a", 0.0412, "invoice")
    assert line["run_cost_usd"] == 0.0412 and line["day_spent_usd"] == 0.0412
    ledger.record("live_a", 0.0873, "voice")  # valor acumulado de la corrida, no suma doble
    snap = ledger.snapshot()
    assert snap["spent_usd"] == 0.0873 and snap["runs"] == 1
    assert snap["per_run"]["live_a"]["steps"] == 2
    assert '"event": "live_run_cost"' in capsys.readouterr().out
    # Un reinicio del servicio lee el mismo registro persistido.
    again = SpendLedger(store, today=lambda: day["d"])
    assert again.snapshot()["spent_usd"] == 0.0873
    day["d"] = "2026-11-04"
    assert again.snapshot()["spent_usd"] == 0 and again.snapshot()["runs"] == 0


def test_ledger_fails_closed_when_store_unreadable():
    ledger = SpendLedger(_FailingStore())
    ok, msg = ledger.allow("live_x")
    assert not ok and "paused" in msg
    assert ledger.snapshot()["ledger_ok"] is False


def test_replay_public_demo_unchanged_by_remote_vars(monkeypatch):
    monkeypatch.setenv("DEMO", "replay")
    monkeypatch.setenv("SHIELD_PANEL_SESSIONS", "1")
    monkeypatch.delenv("SHIELD_LIVE_REMOTE", raising=False)
    monkeypatch.delenv("LIVE_ACCESS_CODE", raising=False)
    client = TestClient(create_panel_app())
    assert client.get("/", follow_redirects=False).status_code == 200
    assert client.post("/live/start").status_code == 403
    assert "not active" in client.get("/live").text
    assert client.get("/live/login").status_code in (404, 405)
