"""Endurecimiento público: guard live, WhatsApp, redacción y docs de FastAPI."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from channels.approvals import ApprovalBroker
from channels.whatsapp import WhatsAppChannel, WhatsAppConfig, create_router
from shield.vault import MemoryVault
from web.app import build_replay_state, create_panel_app
from web.live_chain import LiveChain


def _live_client(monkeypatch):
    monkeypatch.setenv("DEMO", "live")
    chain = LiveChain(vault=MemoryVault({}))
    chain.status = "ready"
    app = create_panel_app(build_replay_state(), live_chain=chain)
    return TestClient(app, raise_server_exceptions=False)


def test_live_guard_rejects_cross_origin_post(monkeypatch):
    client = _live_client(monkeypatch)
    evil = client.post(
        "/live/start", headers={"Origin": "https://evil.example", "Host": "127.0.0.1:8001"}
    )
    assert evil.status_code == 403
    ok = client.post("/live/start", headers={"Host": "127.0.0.1:8001"})
    assert ok.status_code == 200


def test_live_guard_rejects_non_loopback_host_post(monkeypatch):
    client = _live_client(monkeypatch)
    evil = client.post("/live/start", headers={"Host": "evil.example"})
    assert evil.status_code == 403


def test_whatsapp_post_rejected_without_secret_outside_local(monkeypatch):
    monkeypatch.setenv("DEMO", "live")
    monkeypatch.delenv("SHIELD_SANDBOX", raising=False)
    broker = ApprovalBroker()
    channel = WhatsAppChannel(broker, config=WhatsAppConfig())
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(create_router(channel))
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/webhook/whatsapp", content=b"{}", headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 403
    # Sin secreto tampoco vale el verify token por defecto fuera de local.
    assert channel.verify_challenge("subscribe", "shield-demo-verify", "123") is None


def test_whatsapp_simulator_still_works_locally(monkeypatch):
    monkeypatch.setenv("DEMO", "replay")
    broker = ApprovalBroker()
    channel = WhatsAppChannel(broker, config=WhatsAppConfig())
    assert channel.verify_challenge("subscribe", "shield-demo-verify", "123") == "123"
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(create_router(channel))
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/webhook/whatsapp", json={"entry": []})
    assert resp.status_code == 200


def test_live_chain_redacts_all_outputs():
    vault = MemoryVault(
        {"META_MODEL_API_KEY": "meta-secret-123456", "baseten-api-key": "baseten-secret-7890"}
    )
    chain = LiveChain(vault=vault)
    chain._raw_tokens["bodega"] = "shd_bodega_rawtoken123"
    chain.token_store.set_token("bodega", "shd_bodega_refreshed456", "tok_1")
    chain.results["x"] = {"error": "failed Bearer shd_bodega_rawtoken123 and meta-secret-123456"}
    chain.provenance.append({"step": "s", "error": "baseten-secret-7890 Bearer abcdef1234567890"})
    state = json.dumps(chain.state())
    exported = chain.export()
    secrets = (
        "shd_bodega_rawtoken123",
        "shd_bodega_refreshed456",
        "meta-secret-123456",
        "baseten-secret-7890",
        "abcdef1234567890",
    )
    for secret in secrets:
        assert secret not in state, secret
        assert secret not in exported, secret


def test_panel_docs_disabled_outside_local(monkeypatch):
    monkeypatch.setenv("DEMO", "production")
    monkeypatch.delenv("SHIELD_SANDBOX", raising=False)
    app = create_panel_app(build_replay_state())
    assert app.docs_url is None
    assert app.openapi_url is None
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
