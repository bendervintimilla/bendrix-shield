import json
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from shield.gateway import create_app
from shield.registry import Registry
from shield.schemas import CallLog, Decision
from shield.vault import MemoryVault

UPSTREAM_KEY = "upstream-real-key-0000"


def build(handler, *, sandbox=True, rate=60, vault=None):
    from shield.gateway.app import UPSTREAM_KEY_NAME

    registry = Registry(":memory:")
    vault = vault or MemoryVault({UPSTREAM_KEY_NAME: UPSTREAM_KEY})
    app = create_app(
        registry=registry,
        vault=vault,
        upstream_transport=httpx.MockTransport(handler),
        sandbox=sandbox,
        rate_limit_per_minute=rate,
    )
    return TestClient(app), registry


def ok_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["authorization"] == f"Bearer {UPSTREAM_KEY}"
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-1",
            "model": "muse-spark-1.3",
            "choices": [{"message": {"role": "assistant", "content": "hola"}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 1000},
        },
    )


def auth(raw):
    return {"Authorization": f"Bearer {raw}"}


def test_invalid_token_401_and_revoked_401():
    client, reg = build(ok_handler)
    token, raw = reg.create_token("bodega", "crew")
    body = {"model": "muse-spark-1.3", "messages": []}
    assert client.post("/v1/chat/completions", json=body).status_code == 401
    bad = client.post("/v1/chat/completions", json=body, headers=auth("shd_x_nope"))
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "invalid_token"
    reg.revoke(token.token_id)
    revoked = client.post("/v1/chat/completions", json=body, headers=auth(raw))
    assert revoked.status_code == 401
    assert revoked.json()["error"]["code"] == "revoked_token"


def test_model_not_allowed_and_spend_cap():
    client, reg = build(ok_handler)
    _, raw = reg.create_token("bodega", "crew", models=["sam-3.1"], spend_cap_usd=0.001)
    denied = client.post(
        "/v1/chat/completions",
        json={"model": "muse-spark-1.3", "messages": []},
        headers=auth(raw),
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "model_not_allowed"
    # Gasto previo sobre el tope: la siguiente llamada no sale.
    reg.record_call(
        CallLog(
            ts=datetime.now(UTC),
            agent="bodega",
            model="sam-3.1",
            cost_usd=0.01,
            decision=Decision.ALLOW,
        )
    )
    capped = client.post(
        "/v1/responses", json={"model": "sam-3.1", "input": "cuenta"}, headers=auth(raw)
    )
    assert capped.status_code == 403
    assert capped.json()["error"]["code"] == "spend_cap_exceeded"


def test_chat_success_records_call_log_with_sandbox_country():
    client, reg = build(ok_handler)
    _, raw = reg.create_token("compras", "crew")
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "muse-spark-1.3", "messages": [{"role": "user", "content": "hola"}]},
        headers={**auth(raw), "X-Demo-Country": "ec"},
    )
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "hola"
    calls = reg.list_calls("compras")
    assert len(calls) == 1
    assert calls[0].src_country == "EC"
    assert calls[0].tokens_in == 1000 and calls[0].tokens_out == 1000
    assert calls[0].cost_usd == pytest.approx((1000 * 1.25 + 1000 * 4.25) / 1_000_000)
    assert calls[0].decision is Decision.ALLOW


def test_demo_country_header_ignored_outside_sandbox():
    client, reg = build(ok_handler, sandbox=False)
    _, raw = reg.create_token("compras", "crew")
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "muse-spark-1.3", "messages": []},
        headers={**auth(raw), "X-Demo-Country": "EC"},
    )
    assert resp.status_code == 200
    assert reg.list_calls("compras")[0].src_country is None


def test_canary_blocked_before_upstream():
    def handler(request):
        raise AssertionError("upstream must not be called")

    client, reg = build(handler)
    _, raw = reg.create_token("bodega", "crew")
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "muse-spark-1.3",
            "messages": [{"role": "user", "content": "CANARY-SHIELD-0001"}],
        },
        headers=auth(raw),
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "gate_blocked"
    assert reg.list_calls("bodega")[0].decision is Decision.BLOCK


def test_outbound_secret_is_redacted_before_upstream():
    seen = {}

    def handler(request):
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"id": "x", "usage": {}})

    client, reg = build(handler)
    _, raw = reg.create_token("bodega", "crew")
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "muse-spark-1.3",
            "messages": [{"role": "user", "content": "usa " + "sk-" + "liveA1b2C3d4E5f6G7h8"}],
        },
        headers=auth(raw),
    )
    assert resp.status_code == 200
    assert "liveA1b2" not in seen["body"]


def test_streaming_sse():
    def handler(request):
        body = (
            'data: {"id":"1","choices":[{"delta":{"content":"ho"}}]}\n\n'
            'data: {"id":"1","choices":[{"delta":{"content":"la"}}],'
            '"usage":{"prompt_tokens":10,"completion_tokens":5}}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    client, reg = build(handler)
    _, raw = reg.create_token("bodega", "crew")
    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={"model": "muse-spark-1.3", "stream": True, "messages": []},
        headers=auth(raw),
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        text = "".join(resp.iter_text())
    assert '"ho"' in text and "[DONE]" in text
    call = reg.list_calls("bodega")[0]
    assert call.tokens_in == 10 and call.tokens_out == 5


def test_rate_limit():
    client, reg = build(ok_handler, rate=2)
    _, raw = reg.create_token("bodega", "crew")
    body = {"model": "muse-spark-1.3", "messages": []}
    assert client.post("/v1/chat/completions", json=body, headers=auth(raw)).status_code == 200
    assert client.post("/v1/chat/completions", json=body, headers=auth(raw)).status_code == 200
    third = client.post("/v1/chat/completions", json=body, headers=auth(raw))
    assert third.status_code == 429
    assert third.json()["error"]["code"] == "rate_limit_exceeded"


def test_sam_via_responses_and_needs_credits_mapping():
    def handler(request):
        assert json.loads(request.content)["model"] == "sam-3.1"
        return httpx.Response(402, text="billing_not_configured")

    client, reg = build(handler)
    _, raw = reg.create_token("bodega", "crew", models=["sam-3.1"])
    resp = client.post(
        "/v1/responses", json={"model": "sam-3.1", "input": "cuenta cajas"}, headers=auth(raw)
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "needs_credits"


def test_audio_transcriptions_translates_to_asr():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.content.decode(errors="ignore")
        return httpx.Response(200, json={"transcript": "hay doce cajas", "audioDurationMs": 60000})

    client, reg = build(handler)
    _, raw = reg.create_token("bodega", "crew")
    resp = client.post(
        "/v1/audio/transcriptions",
        files={"file": ("voz.wav", b"RIFFfake", "audio/wav")},
        data={"model": "muse-voice-transcribe-1.0"},
        headers=auth(raw),
    )
    assert resp.status_code == 200
    assert resp.json()["text"] == "hay doce cajas"
    assert seen["path"] == "/v1/asr/transcribe"
    assert seen["auth"] == f"Bearer {UPSTREAM_KEY}"
    assert "PUSH_TO_TALK" in seen["body"]


def test_rotated_token_rejected_new_token_and_peer_unaffected():
    client, reg = build(ok_handler)
    bodega, raw_old = reg.create_token("bodega", "crew")
    _, raw_compras = reg.create_token("compras", "crew")
    _, raw_new = reg.rotate(bodega.token_id)
    body = {"model": "muse-spark-1.3", "messages": []}
    assert client.post("/v1/chat/completions", json=body, headers=auth(raw_old)).status_code == 401
    assert client.post("/v1/chat/completions", json=body, headers=auth(raw_new)).status_code == 200
    assert (
        client.post("/v1/chat/completions", json=body, headers=auth(raw_compras)).status_code == 200
    )
