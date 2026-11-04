"""TokenOps real (shield.actions + Registry): el token robado pasa a 401."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from fastapi.testclient import TestClient

from shield.actions import Actions
from shield.autopilot import ContainmentEngine, SecurityEvent, run_pipeline
from shield.autopilot.respond import ShieldActionsTokenOps
from shield.gateway.app import UPSTREAM_KEY_NAME, create_app
from shield.registry import Registry
from shield.sdk.token_store import LocalTokenStore
from shield.vault import MemoryVault

UPSTREAM_KEY = "upstream-real-key-0000"
T0 = datetime(2026, 11, 4, 3, 0, tzinfo=UTC)


def ok_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["authorization"] == f"Bearer {UPSTREAM_KEY}"
    return httpx.Response(200, json={
        "id": "chatcmpl-1", "model": "muse-spark-1.3",
        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5}})


def post(client, raw):
    return client.post("/v1/chat/completions",
                       json={"model": "muse-spark-1.3",
                             "messages": [{"role": "user", "content": "hola"}]},
                       headers={"Authorization": f"Bearer {raw}"})


def test_token_robado_200_a_401_y_pares_siguen(tmp_path):
    registry = Registry(":memory:")
    app = create_app(registry=registry,
                     vault=MemoryVault({UPSTREAM_KEY_NAME: UPSTREAM_KEY}),
                     upstream_transport=httpx.MockTransport(ok_handler),
                     sandbox=True)
    client = TestClient(app)
    store = LocalTokenStore(tmp_path / "tokens.json")
    _, stolen_raw = registry.create_token("crew-bot", "crew")
    _, peer_raw = registry.create_token("compras", "crew")
    store.set_token("crew-bot", stolen_raw, "x")
    assert post(client, stolen_raw).status_code == 200
    assert post(client, peer_raw).status_code == 200

    # Ráfaga del token robado -> autopiloto revoca SOLO ese agente (vía actions).
    events = [SecurityEvent.from_dict({
        "app": "ai_gateway", "actor": "crew-bot", "action": "model_call",
        "target": "muse-spark-1.3", "source": "attacker", "token_id": "tok-stolen",
        "ts": (T0 + timedelta(seconds=5 * i)).isoformat()}) for i in range(12)]
    actions = Actions(registry=registry, token_store=store, auto_contain=True)
    engine = ContainmentEngine(token_ops=ShieldActionsTokenOps(actions))
    _, result = run_pipeline(events, engine=engine)
    assert result.scope_level in ("app", "global", "actor")

    assert post(client, stolen_raw).status_code == 401  # token robado muerto
    assert post(client, peer_raw).status_code == 200  # el par no se toca
