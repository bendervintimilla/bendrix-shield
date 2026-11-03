"""d · voz contra repetición: una grabación del dueño vale para un solo plan."""

from __future__ import annotations

import time

from channels.whatsapp import VOICE_CLOCK_SKEW_S, parse_webhook
from tests.test_live_h14 import _wav_bytes, make_chain
from tests.test_whatsapp_live_voice import (
    FakeHTTP,
    RecordingChain,
    _audio_payload,
    _channel,
)
from web.live_chain import audio_fingerprint


def _run_to_guardian(chain):
    chain.step_count()
    chain.step_attack()
    assert chain.step_guardian()["status"] == "ok"


def test_same_recording_cannot_approve_the_next_plan():
    chain, handler = make_chain()
    try:
        _run_to_guardian(chain)
        first = chain.step_voice(wav_bytes=_wav_bytes())
        assert first["status"] == "approved", first
        used_for = first["approval_id"]

        chain.reset()  # New run: plan nuevo, nonce nuevo
        _run_to_guardian(chain)
        calls_before = len(handler.calls)
        replay = chain.step_voice(wav_bytes=_wav_bytes())
        assert replay["status"] == "replayed"
        assert used_for in replay["error"]
        assert len(handler.calls) == calls_before, "la repetición no gasta transcripción"
        assert chain.state()["results"]["voice"]["status"] == "replayed"
        assert not chain.broker.is_approved(chain._approval_id)

        fresh = chain.step_voice(wav_bytes=_wav_bytes(text_frames=1700))
        assert fresh["status"] == "approved", fresh
    finally:
        chain.close()


def test_fingerprint_ignores_header_and_typed_fallback_is_not_blocked():
    a = _wav_bytes()
    assert audio_fingerprint(a) == audio_fingerprint(a[:44] + a[44:])
    assert audio_fingerprint(a) != audio_fingerprint(_wav_bytes(text_frames=1601))
    chain, _h = make_chain()
    try:
        _run_to_guardian(chain)
        assert chain.step_voice(wav_bytes=b"not a wav")["status"] == "error"
        assert chain._voice_used == {}, "un audio inválido no queda registrado"
    finally:
        chain.close()


class IssuedChain(RecordingChain):
    def __init__(self, issued_at):
        super().__init__()
        self._issued_at = issued_at

    def voice_issued_at(self):
        return self._issued_at


def _with(payload, **fields):
    payload["entry"][0]["changes"][0]["value"]["messages"][0].update(fields)
    return payload


def test_parse_timestamp_and_forwarded():
    msg = parse_webhook(_with(_audio_payload(), timestamp="1730000000",
                              context={"forwarded": True}))[0]
    assert msg.timestamp == 1730000000.0 and msg.forwarded is True
    plain = parse_webhook(_audio_payload())[0]
    assert plain.timestamp == 0.0 and plain.forwarded is False


def test_forwarded_voice_note_is_rejected_without_download():
    chain = IssuedChain(time.time())
    http = FakeHTTP()
    channel = _channel(chain, http)
    out = channel.handle_payload(_with(_audio_payload(message_id="wamid.f"),
                                       context={"frequently_forwarded": True}))
    assert out[0]["reason"] == "forwarded"
    assert http.gets == [] and chain.voice_calls == []
    assert chain.errors and "forwarded" in chain.errors[0][0]


def test_voice_note_older_than_plan_is_rejected():
    issued = time.time()
    chain = IssuedChain(issued)
    http = FakeHTTP()
    channel = _channel(chain, http)
    old = str(int(issued - VOICE_CLOCK_SKEW_S - 60))
    out = channel.handle_payload(_with(_audio_payload(message_id="wamid.o"), timestamp=old))
    assert out[0]["reason"] == "older_than_plan"
    assert http.gets == [] and chain.voice_calls == []
    # Dentro del margen de reloj sí pasa.
    ok = str(int(issued - 1))
    done = channel.handle_payload(_with(_audio_payload(message_id="wamid.n"), timestamp=ok))
    assert done[0]["status"] == "approved"


def test_replayed_status_is_reported_to_owner():
    class ReplayChain(RecordingChain):
        def step_voice(self, wav_bytes=None, typed=None, channel="browser"):
            self.voice_calls.append({"channel": channel})
            return {
                "status": "replayed",
                "error": "this exact recording was already used for pend_1",
            }

    chain = ReplayChain()
    http = FakeHTTP()
    out = _channel(chain, http).handle_payload(_audio_payload(message_id="wamid.r"))
    assert out[0]["status"] == "replayed"
    assert chain.contain_calls == 0
    assert any("already used" in p["json"]["text"]["body"] for p in http.posts)
