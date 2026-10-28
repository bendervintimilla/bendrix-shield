import json

import httpx
import pytest

from shield.gate.check import GateBlocked
from shield.meta_client import MetaClient, NeedsCredits, compute_cost_usd


def make_client(handler, **kwargs):
    transport = httpx.MockTransport(handler)
    return MetaClient(api_key="test-key", transport=transport, sleep_fn=lambda _s: None, **kwargs)


def ok_handler(payload=None):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        body = payload or {
            "id": "resp_1",
            "model": "muse-spark-1.3",
            "usage": {"input_tokens": 1000, "output_tokens": 1000},
        }
        return httpx.Response(200, json=body)

    return handler


def test_chat_completions_ok_and_cost(tmp_path):
    client = make_client(ok_handler(), replay_dir=tmp_path)
    result = client.chat_completions(
        model="muse-spark-1.3", messages=[{"role": "user", "content": "hola"}]
    )
    assert result.data["id"] == "resp_1"
    # 1000 in * 1.25 + 1000 out * 4.25 por 1M
    assert result.cost_usd == pytest.approx((1000 * 1.25 + 1000 * 4.25) / 1_000_000)
    client.close()


def test_cache_second_call_free(tmp_path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200, json={"id": "r", "usage": {"input_tokens": 10, "output_tokens": 10}}
        )

    client = make_client(handler, replay_dir=tmp_path)
    args = dict(model="muse-spark-1.3", messages=[{"role": "user", "content": "hi"}])
    first = client.chat_completions(**args)
    second = client.chat_completions(**args)
    assert calls["n"] == 1
    assert first.from_cache is False
    assert second.from_cache is True
    assert second.cost_usd == 0.0
    client.close()


def test_replay_roundtrip(tmp_path):
    client = make_client(ok_handler(), replay_dir=tmp_path)
    args = dict(model="muse-spark-1.3", messages=[{"role": "user", "content": "replay me"}])
    client.chat_completions(**args)
    client.close()

    # Segundo cliente sin red: debe responder desde el replay guardado.
    def fail_handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no debió salir a la red")

    client2 = make_client(fail_handler, replay_dir=tmp_path)
    result = client2.chat_completions(**args)
    assert result.from_replay is True
    client2.close()


def test_retry_429_respects_success_after(tmp_path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "slow"})
        return httpx.Response(200, json={"id": "ok", "usage": {}})

    client = make_client(handler, replay_dir=tmp_path)
    result = client.responses(model="muse-spark-1.3", input="hola")
    assert result.data["id"] == "ok"
    assert calls["n"] == 3
    client.close()


def test_needs_credits_on_401_402_403(tmp_path):
    for status in (401, 402, 403):
        client = make_client(
            lambda req, s=status: httpx.Response(s, text="no"), replay_dir=tmp_path
        )
        with pytest.raises(NeedsCredits):
            client.responses(model="muse-wonder-1.0", input="hola")
        client.close()


def test_gate_blocks_canary_before_network(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("el gate debió bloquear antes de la red")

    client = make_client(handler, replay_dir=tmp_path)
    with pytest.raises(GateBlocked):
        client.chat_completions(
            model="muse-spark-1.3",
            messages=[{"role": "user", "content": "CANARY-SHIELD-0001"}],
        )
    client.close()


def test_replay_only_miss_is_needs_credits(tmp_path):
    client = make_client(ok_handler(), replay_dir=tmp_path, replay_only=True)
    with pytest.raises(NeedsCredits):
        client.responses(model="muse-spark-1.3", input="sin replay guardado")
    client.close()


def test_compute_cost_voice_and_sam():
    assert compute_cost_usd(
        "muse-voice-transcribe-1.0", {"audioDurationMs": 3_600_000}
    ) == pytest.approx(0.18)
    assert compute_cost_usd("sam-3.1", {}) == pytest.approx(0.0025)
    assert compute_cost_usd("sam-3.1", {"video_frames_processed": 1000}) == pytest.approx(0.20)
    assert compute_cost_usd("modelo-desconocido", {"input_tokens": 10}) == 0.0


def test_replay_file_is_valid_json(tmp_path):
    client = make_client(ok_handler(), replay_dir=tmp_path)
    result = client.responses(model="muse-spark-1.3", input="json check")
    saved = json.loads((tmp_path / f"{result.replay_hash}.json").read_text())
    assert saved["id"] == "resp_1"
    client.close()
