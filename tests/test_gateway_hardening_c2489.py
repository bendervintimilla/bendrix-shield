"""C2489-3: endurecimiento del gateway.

Controles: alcance mínimo por token (verbo/ruta/rangos), tasa por token,
anti-repetición (nonce + ventana de tiempo), auditoría con cadena de hash
y revocación de emergencia. Todo offline con upstream falso.
"""

import time
from datetime import UTC, datetime

import httpx
from fastapi.testclient import TestClient

from shield.gateway import create_app
from shield.registry import Registry
from shield.schemas import CallLog, Decision
from shield.vault import MemoryVault

UPSTREAM_KEY = "upstream-real-key-0000"


def ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-1",
            "model": "muse-spark-1.3",
            "choices": [{"message": {"role": "assistant", "content": "hola"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10},
        },
    )


def build(handler=ok_handler, *, rate=60):
    from shield.gateway.app import UPSTREAM_KEY_NAME

    registry = Registry(":memory:")
    vault = MemoryVault({UPSTREAM_KEY_NAME: UPSTREAM_KEY})
    app = create_app(
        registry=registry,
        vault=vault,
        upstream_transport=httpx.MockTransport(handler),
        sandbox=True,
        rate_limit_per_minute=rate,
    )
    return TestClient(app), registry


def auth(raw, **extra):
    return {"Authorization": f"Bearer {raw}", **extra}


BODY = {"model": "muse-spark-1.3", "messages": []}


# -- 1. Alcance mínimo: verbo + ruta ----------------------------------------


def test_scope_blocks_route_not_in_allowlist():
    client, reg = build()
    _, raw = reg.create_token("nevera", "crew", allowed_routes=["POST /v1/chat/completions"])
    assert client.post("/v1/chat/completions", json=BODY, headers=auth(raw)).status_code == 200
    denied = client.post("/v1/responses", json=BODY, headers=auth(raw))
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "route_not_allowed"


def test_scope_empty_allowlist_is_backward_compatible():
    client, reg = build()
    _, raw = reg.create_token("bodega", "crew")
    assert client.post("/v1/chat/completions", json=BODY, headers=auth(raw)).status_code == 200
    assert client.post("/v1/responses", json=BODY, headers=auth(raw)).status_code == 200


def test_scope_legacy_scopes_field_also_enforced():
    client, reg = build()
    _, raw = reg.create_token("nevera", "crew", scopes=["POST:/v1/chat/completions"])
    assert client.post("/v1/chat/completions", json=BODY, headers=auth(raw)).status_code == 200
    denied = client.post("/v1/responses", json=BODY, headers=auth(raw))
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "route_not_allowed"


def test_scope_wrong_verb_blocked():
    client, reg = build()
    # Solo lectura sobre la ruta: el POST de escritura queda fuera.
    _, raw = reg.create_token("nevera", "crew", allowed_routes=["GET /v1/chat/completions"])
    denied = client.post("/v1/chat/completions", json=BODY, headers=auth(raw))
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "route_not_allowed"


# -- 1b. Alcance mínimo: rangos de valores -----------------------------------


def test_numeric_limit_blocks_out_of_range_setpoint():
    client, reg = build()
    _, raw = reg.create_token(
        "nevera", "crew", numeric_limits={"setpoint_c": [-25.0, 5.0], "temperature": [0.0, 1.0]}
    )
    ok = client.post(
        "/v1/chat/completions",
        json={**BODY, "setpoint_c": -18.0},
        headers=auth(raw),
    )
    assert ok.status_code == 200
    denied = client.post(
        "/v1/chat/completions",
        json={**BODY, "setpoint_c": 22.0},
        headers=auth(raw),
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "value_out_of_range"


def test_numeric_limit_blocks_nested_and_temperature():
    client, reg = build()
    _, raw = reg.create_token("nevera", "crew", numeric_limits={"temperature": [0.0, 1.0]})
    denied = client.post(
        "/v1/chat/completions",
        json={**BODY, "temperature": 9.9},
        headers=auth(raw),
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "value_out_of_range"


# -- 2. Tasa por token --------------------------------------------------------


def test_per_token_rate_limit_overrides_global():
    client, reg = build(rate=60)
    _, raw_lento = reg.create_token("nevera", "crew", rate_limit_per_minute=2)
    _, raw_normal = reg.create_token("bodega", "crew")
    assert (
        client.post("/v1/chat/completions", json=BODY, headers=auth(raw_lento)).status_code == 200
    )
    assert (
        client.post("/v1/chat/completions", json=BODY, headers=auth(raw_lento)).status_code == 200
    )
    third = client.post("/v1/chat/completions", json=BODY, headers=auth(raw_lento))
    assert third.status_code == 429
    assert third.json()["error"]["code"] == "rate_limit_exceeded"
    # El otro token no se ve afectado por el límite ajeno.
    assert (
        client.post("/v1/chat/completions", json=BODY, headers=auth(raw_normal)).status_code == 200
    )
    assert (
        client.post("/v1/chat/completions", json=BODY, headers=auth(raw_normal)).status_code == 200
    )


# -- 3. Anti-repetición: nonce + ventana --------------------------------------


def _nonce_headers(nonce="nonce-1", ts=None):
    return {
        "X-Shield-Nonce": nonce,
        "X-Shield-Timestamp": str(int(time.time()) if ts is None else ts),
    }


def test_nonce_required_replay_and_stale():
    client, reg = build()
    _, raw = reg.create_token("nevera", "crew", require_nonce=True)
    # Sin nonce: rechazado.
    missing = client.post("/v1/chat/completions", json=BODY, headers=auth(raw))
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "nonce_required"
    # Primera vez con nonce válido: pasa.
    first = client.post(
        "/v1/chat/completions", json=BODY, headers=auth(raw, **_nonce_headers("n-1"))
    )
    assert first.status_code == 200
    # Repetición del mismo nonce: bloqueada (ataque de replay / setpoint repetido).
    replay = client.post(
        "/v1/chat/completions", json=BODY, headers=auth(raw, **_nonce_headers("n-1"))
    )
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "replay_detected"
    # Nonce nuevo pero marca de tiempo vieja (>5 min): bloqueada.
    stale = client.post(
        "/v1/chat/completions",
        json=BODY,
        headers=auth(raw, **_nonce_headers("n-2", ts=int(time.time()) - 3600)),
    )
    assert stale.status_code == 401
    assert stale.json()["error"]["code"] == "stale_timestamp"
    # Token sin require_nonce no exige headers (compatibilidad).
    _, raw2 = reg.create_token("bodega", "crew")
    assert client.post("/v1/chat/completions", json=BODY, headers=auth(raw2)).status_code == 200


# -- 4. Auditoría con cadena de hash + revocación de emergencia ----------------


def test_audit_chain_detects_tampering():
    client, reg = build()
    _, raw = reg.create_token("bodega", "crew")
    for _ in range(3):
        assert client.post("/v1/chat/completions", json=BODY, headers=auth(raw)).status_code == 200
    ok, broken_at = reg.verify_audit_chain()
    assert ok is True
    assert broken_at is None
    calls = reg.list_calls("bodega")
    assert len(calls) == 3
    assert all(c.entry_hash for c in calls)
    assert calls[0].prev_hash == "0" * 64
    assert calls[1].prev_hash == calls[0].entry_hash
    # Manipulación directa en la base: la cadena debe romperse.
    with reg._lock, reg._conn:
        reg._conn.execute(
            "UPDATE call_logs SET cost_usd=999 WHERE id=(SELECT MIN(id) FROM call_logs)"
        )
    ok2, broken2 = reg.verify_audit_chain()
    assert ok2 is False
    assert broken2 is not None


def test_emergency_revoke_all_only_affects_scope():
    client, reg = build()
    _, raw_a = reg.create_token("bodega", "crew")
    _, raw_b = reg.create_token("compras", "crew")
    _, raw_c = reg.create_token("nevera", "iot")
    assert reg.revoke_all(agent="bodega") == 1
    assert client.post("/v1/chat/completions", json=BODY, headers=auth(raw_a)).status_code == 401
    assert client.post("/v1/chat/completions", json=BODY, headers=auth(raw_b)).status_code == 200
    # Revocación total de emergencia.
    assert reg.revoke_all() == 2
    assert client.post("/v1/chat/completions", json=BODY, headers=auth(raw_b)).status_code == 401
    assert client.post("/v1/chat/completions", json=BODY, headers=auth(raw_c)).status_code == 401


def test_rotate_preserves_hardening_fields():
    reg = Registry(":memory:")
    tok, raw = reg.create_token(
        "nevera",
        "crew",
        allowed_routes=["POST /v1/chat/completions"],
        numeric_limits={"setpoint_c": [-25.0, 5.0]},
        rate_limit_per_minute=5,
        require_nonce=True,
    )
    rotated, _raw_new = reg.rotate(tok.token_id)
    assert rotated is not None
    assert rotated.allowed_routes == ["POST /v1/chat/completions"]
    assert rotated.numeric_limits == {"setpoint_c": [-25.0, 5.0]}
    assert rotated.rate_limit_per_minute == 5
    assert rotated.require_nonce is True
    reg.close()


def test_audit_chain_survives_direct_record_call():
    reg = Registry(":memory:")
    reg.create_token("bodega", "crew")
    reg.record_call(
        CallLog(
            ts=datetime.now(UTC), agent="bodega", model="m", cost_usd=0.1, decision=Decision.ALLOW
        )
    )
    reg.record_call(
        CallLog(
            ts=datetime.now(UTC), agent="bodega", model="m", cost_usd=0.2, decision=Decision.BLOCK
        )
    )
    ok, _ = reg.verify_audit_chain()
    assert ok is True
    reg.close()
