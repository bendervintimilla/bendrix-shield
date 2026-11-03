"""WhatsApp voice-note approvals en la cadena live (offline, sin red)."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import shutil
import subprocess
import wave

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from channels.approvals import ApprovalBroker
from channels.whatsapp import (
    WhatsAppChannel,
    WhatsAppConfig,
    convert_audio_to_wav,
    create_router,
    is_allowed_media_url,
)
from shield.vault import MemoryVault
from web.live_chain import LiveChain, validate_wav
from web.live_page import render_live_page

SECRET = "app-secret-prueba"
OWNER = "593991112233"
OTHER = "593980000000"


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def _wav_bytes() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 1600)
    return buf.getvalue()


def _ogg_bytes() -> bytes:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg no disponible")
    proc = subprocess.run(
        [
            ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2",
            "-c:a", "libopus", "-f", "ogg", "pipe:1",
        ],
        capture_output=True, timeout=30, check=False,
    )
    if proc.returncode != 0 or not proc.stdout:
        pytest.skip("ffmpeg sin libopus")
    return proc.stdout


class _Resp:
    def __init__(self, *, status_code=200, data=None, content=b""):
        self.status_code = status_code
        self._data = data or {}
        self.content = content

    def json(self):
        return self._data


class FakeHTTP:
    """Cliente HTTP falso: registra GET/POST, nunca sale a la red."""

    def __init__(self, media_url="https://lookaside.fbsbx.com/wa/media.ogg", media=b"ogg-fake"):
        self.media_url = media_url
        self.media = media
        self.gets: list[str] = []
        self.posts: list[dict] = []

    def get(self, url, headers=None):
        self.gets.append(url)
        if "/media-" in url or url.endswith("/media1"):
            return _Resp(data={"url": self.media_url})
        # lookup Graph /{media_id}
        if "graph.facebook.com" in url:
            return _Resp(data={"url": self.media_url})
        return _Resp(content=self.media)

    def post(self, url, json=None, headers=None):
        self.posts.append({"url": url, "json": json, "headers": headers})
        return _Resp(status_code=200)


class FakeChain:
    def __init__(self, voice_status="approved"):
        self._approval_id = "pend_test"
        self.voice_status = voice_status
        self.voice_calls: list[dict] = []
        self.confirm_calls: list = []
        self.contain_calls = 0

    def step_voice(self, wav_bytes=None, typed=None, channel="browser"):
        self.voice_calls.append({"wav_bytes": wav_bytes, "typed": typed, "channel": channel})
        return {
            "status": self.voice_status,
            "transcript": "yes, rotate it",
            "channel": channel,
            "intent": {"action": "approve", "exclude_targets": [], "only_targets": []},
        }

    def step_voice_confirm(self, channel=None):
        self.confirm_calls.append(channel)
        return {"status": "approved", "channel": channel}

    def step_contain(self):
        self.contain_calls += 1
        return {
            "status": "ok",
            "attacker_after": [401],
            "sdk_statuses": [401, 200],
            "contained_in_s": 3.5,
        }


def _audio_payload(message_id="wamid.1", from_number=OWNER, media_id="media1", kind="audio"):
    key = "audio" if kind == "audio" else "voice"
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"messages": [
            {"id": message_id, "from": from_number, "type": kind, key: {"id": media_id}},
        ]}}]}],
    }


def _text_payload(message_id="wamid.t1", from_number=OWNER, body="confirm"):
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"messages": [
            {"id": message_id, "from": from_number, "type": "text", "text": {"body": body}},
        ]}}]}],
    }


def _channel(chain, http, **kw):
    return WhatsAppChannel(
        ApprovalBroker(),
        config=WhatsAppConfig(
            phone_number=OWNER, token="tok-prueba", phone_number_id="123",
            app_secret=SECRET,
        ),
        http_client=http,
        live_chain_getter=lambda: chain,
        audio_converter=kw.pop("audio_converter", lambda b: _wav_bytes()),
        **kw,
    )


def test_allowed_media_hosts():
    assert is_allowed_media_url("https://lookaside.fbsbx.com/x")
    assert is_allowed_media_url("https://media.whatsapp.net/x")
    assert is_allowed_media_url("https://scontent.fbcdn.net/x")
    assert not is_allowed_media_url("https://evil.example/x")
    assert not is_allowed_media_url("http://lookaside.fbsbx.com/x")


def test_audio_owner_calls_step_voice_with_wav_and_contains():
    chain = FakeChain()
    http = FakeHTTP()
    channel = _channel(chain, http)
    results = channel.handle_payload(_audio_payload())
    assert results[0]["status"] == "approved"
    assert len(chain.voice_calls) == 1
    assert chain.voice_calls[0]["channel"] == "whatsapp"
    assert validate_wav(chain.voice_calls[0]["wav_bytes"])["ok"]
    assert chain.contain_calls == 1
    # Respuesta al dueño con transcripción y resultado.
    bodies = [p["json"]["text"]["body"] for p in http.posts]
    assert any("yes, rotate it" in b and "401" in b and "3.5s" in b for b in bodies)


def test_audio_voice_type_also_accepted():
    chain = FakeChain()
    channel = _channel(chain, FakeHTTP())
    results = channel.handle_payload(_audio_payload(message_id="wamid.v", kind="voice"))
    assert results[0]["status"] == "approved"
    assert len(chain.voice_calls) == 1


def test_foreign_number_ignored_without_download():
    chain = FakeChain()
    http = FakeHTTP()
    channel = _channel(chain, http)
    results = channel.handle_payload(_audio_payload(from_number=OTHER))
    assert results[0]["status"] == "ignored" and results[0]["reason"] == "not_owner"
    assert http.gets == [] and chain.voice_calls == []


def test_media_domain_not_allowed_rejected():
    chain = FakeChain()
    http = FakeHTTP(media_url="https://evil.example/nota.ogg")
    channel = _channel(chain, http)
    results = channel.handle_payload(_audio_payload())
    assert results[0]["status"] == "error"
    assert "not allowed" in results[0]["error"]
    assert chain.voice_calls == []
    assert all("evil.example" not in u for u in http.gets)


def test_idempotent_by_message_id():
    chain = FakeChain()
    channel = _channel(chain, FakeHTTP())
    first = channel.handle_payload(_audio_payload())
    second = channel.handle_payload(_audio_payload())
    assert first[0]["status"] == "approved"
    assert second[0]["status"] == "duplicate"
    assert len(chain.voice_calls) == 1 and chain.contain_calls == 1


def test_partial_asks_confirm_then_text_confirm_contains():
    chain = FakeChain(voice_status="confirmation_required")
    http = FakeHTTP()
    channel = _channel(chain, http)
    results = channel.handle_payload(_audio_payload(message_id="wamid.p"))
    assert results[0]["status"] == "confirmation_required"
    assert chain.contain_calls == 0
    bodies = [p["json"]["text"]["body"] for p in http.posts]
    assert any("confirm" in b.lower() for b in bodies)
    done = channel.handle_payload(_text_payload())
    assert done[0]["status"] == "approved"
    assert chain.confirm_calls == ["whatsapp"]
    assert chain.contain_calls == 1


def test_text_confirm_foreign_ignored():
    chain = FakeChain()
    channel = _channel(chain, FakeHTTP())
    results = channel.handle_payload(_text_payload(from_number=OTHER))
    assert results[0]["status"] == "ignored"
    assert chain.confirm_calls == []


def test_real_ffmpeg_ogg_to_wav():
    ogg = _ogg_bytes()
    chain = FakeChain()
    http = FakeHTTP(media=ogg)
    channel = _channel(chain, http, audio_converter=convert_audio_to_wav)
    results = channel.handle_payload(_audio_payload())
    assert results[0]["status"] == "approved"
    assert validate_wav(chain.voice_calls[0]["wav_bytes"])["ok"]


def test_signature_valid_invalid_and_secret_required_in_live(monkeypatch):
    chain = FakeChain()
    http = FakeHTTP()
    channel = _channel(chain, http)
    app = FastAPI()
    app.include_router(create_router(channel))
    client = TestClient(app, raise_server_exceptions=False)
    raw = json.dumps(_text_payload(message_id="wamid.s1")).encode()
    bad = client.post("/webhook/whatsapp", content=raw,
                      headers={"x-hub-signature-256": "sha256=00"})
    assert bad.status_code == 403
    good = client.post("/webhook/whatsapp", content=raw,
                       headers={"x-hub-signature-256": _sign(raw)})
    assert good.status_code == 200
    channel.wait_for_background(timeout=5)
    assert chain.confirm_calls == ["whatsapp"]  # procesado en fondo, 200 rápido

    # Sin app-secret con credenciales reales: rechazar aunque sea local.
    monkeypatch.setenv("DEMO", "replay")
    no_secret = WhatsAppChannel(
        ApprovalBroker(),
        config=WhatsAppConfig(phone_number=OWNER, token="t", phone_number_id="1"),
    )
    app2 = FastAPI()
    app2.include_router(create_router(no_secret))
    client2 = TestClient(app2, raise_server_exceptions=False)
    assert client2.post("/webhook/whatsapp", content=b"{}").status_code == 403


def test_plan_message_sent_live_and_simulator_outbox():
    plan = {
        "summary": "Rotate bodega token",
        "steps": [{"action": "rotate_token", "target": "bodega"}],
    }
    http = FakeHTTP()
    channel = _channel(FakeChain(), http)
    sent = channel.notify_guardian_plan(plan, approval_id="pend_1")
    assert sent["simulated"] is False
    assert http.posts and http.posts[-1]["json"]["to"] == OWNER
    body = http.posts[-1]["json"]["text"]["body"]
    assert "Rotate bodega token" in body
    assert "Reply with a voice note" in body and "yes, rotate it" in body

    sim = WhatsAppChannel(ApprovalBroker(), config=WhatsAppConfig())
    sent2 = sim.notify_guardian_plan(plan)
    assert sent2["simulated"] is True and sim.outbox
    assert "yes, rotate it" in sim.outbox[-1]["text"]["body"]


def test_guardian_endpoint_sends_plan_to_owner(monkeypatch):
    from web.app import build_replay_state, create_panel_app

    monkeypatch.setenv("DEMO", "live")

    class GuardianChain(FakeChain):
        def step_guardian(self):
            return {
                "status": "ok",
                "approval_id": "pend_test",
                "plan": {
                    "summary": "Rotate bodega token",
                    "steps": [{"action": "rotate_token", "target": "bodega"}],
                },
            }

    chain = GuardianChain()
    app = create_panel_app(build_replay_state(), live_chain=chain)
    sim = WhatsAppChannel(ApprovalBroker(), config=WhatsAppConfig(phone_number=OWNER))
    app.state.whatsapp = sim
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/live/step/guardian")
    assert resp.status_code == 200
    assert sim.outbox, "sin credenciales el plan queda en outbox (simulador)"
    assert "yes, rotate it" in sim.outbox[-1]["text"]["body"]


def test_live_chain_state_voice_channel():
    chain = LiveChain(vault=MemoryVault({}))
    broker = chain.broker
    req = broker.request({"summary": "plan", "steps": [
        {"action": "rotate_token", "target": "bodega", "requires_approval": True},
    ]})
    chain._approval_id = req.approval_id
    out = chain.step_voice(typed="yes, rotate it", channel="whatsapp")
    assert out["channel"] == "whatsapp"
    state = chain.state()
    assert state["voice"]["channel"] == "whatsapp"
    assert state["results"]["voice"]["channel"] == "whatsapp"


def test_live_startup_whatsapp_channel_uses_fake_vault(monkeypatch):
    from shield.vault import MemoryVault
    from web.app import build_replay_state, create_panel_app

    fake = MemoryVault(
        {
            "whatsapp-test-verify-token": "verify-falso",
            "whatsapp-app-secret": "secret-falso",
            "whatsapp-test-phone": OWNER,
            "whatsapp-test-token": "tok-falso",
            "whatsapp-test-phone-id": "123",
        }
    )
    monkeypatch.setenv("DEMO", "live")
    monkeypatch.setattr("web.app.get_vault", lambda *a, **k: fake, raising=False)
    monkeypatch.setattr(
        "shield.vault.vault.get_vault", lambda *a, **k: fake, raising=False
    )
    app = create_panel_app(build_replay_state())
    client = TestClient(app, raise_server_exceptions=False)
    # Sin abrir /live: la verificación GET ya responde con el vault.
    ok = client.get(
        "/webhook/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-falso",
            "hub.challenge": "12345",
        },
    )
    assert ok.status_code == 200 and ok.text == "12345"
    # Y la firma POST se valida con el secreto falso del vault.
    raw = b"{}"
    sig = "sha256=" + hmac.new(b"secret-falso", raw, hashlib.sha256).hexdigest()
    signed = client.post(
        "/webhook/whatsapp", content=raw, headers={"x-hub-signature-256": sig}
    )
    assert signed.status_code == 200
    bad = client.post(
        "/webhook/whatsapp", content=raw, headers={"x-hub-signature-256": "sha256=00"}
    )
    assert bad.status_code == 403


def test_live_startup_whatsapp_falls_back_when_vault_fails(monkeypatch):
    from web.app import build_replay_state, create_panel_app

    def boom(*a, **k):
        raise RuntimeError("vault no disponible")

    monkeypatch.setenv("DEMO", "live")
    monkeypatch.setattr("web.app.get_vault", boom, raising=False)
    monkeypatch.setattr("shield.vault.vault.get_vault", boom, raising=False)
    for name in (
        "WHATSAPP_TEST_PHONE",
        "WHATSAPP_TEST_TOKEN",
        "WHATSAPP_VERIFY_TOKEN",
        "WHATSAPP_APP_SECRET",
        "WHATSAPP_PHONE_NUMBER_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    app = create_panel_app(build_replay_state())
    assert app.state.whatsapp.config.verify_token is None
    assert app.state.whatsapp.config.app_secret is None


def test_new_run_reloads_page():
    html = render_live_page("en")
    assert "newRunBtn" in html
    handler = html.split('byId("newRunBtn").addEventListener')[1][:300]
    assert "/reset" in handler and "location.reload" in handler
    assert "voiceChannel" in html
    assert "Owner approved via WhatsApp voice note" in html


class RecordingChain(FakeChain):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.errors: list[tuple[str, str]] = []

    def record_voice_error(self, error, channel="whatsapp"):
        self.errors.append((error, channel))
        return {"status": "error", "error": error, "channel": channel}


def test_download_failure_is_visible_in_panel_and_owner_gets_reply():
    class Expired(FakeHTTP):
        def get(self, url, headers=None):
            self.gets.append(url)
            return _Resp(status_code=401)

    chain = RecordingChain()
    http = Expired()
    channel = _channel(chain, http)
    results = channel.handle_payload(_audio_payload(message_id="wamid.e1"))
    assert results[0]["status"] == "error"
    assert chain.voice_calls == []
    assert len(chain.errors) == 1
    assert "401" in chain.errors[0][0] and chain.errors[0][1] == "whatsapp"
    bodies = [p["json"]["text"]["body"] for p in http.posts]
    assert any("could not process the voice note" in b for b in bodies)
    assert all("tok-prueba" not in b for b in bodies)


def test_voice_note_without_pending_plan_is_visible():
    chain = RecordingChain()
    chain._approval_id = None
    http = FakeHTTP()
    channel = _channel(chain, http)
    results = channel.handle_payload(_audio_payload(message_id="wamid.e2"))
    assert results[0]["reason"] == "no pending approval"
    assert http.gets == []
    assert chain.errors and "no plan is pending" in chain.errors[0][0]
    assert any("Guardian" in p["json"]["text"]["body"] for p in http.posts)


def test_live_chain_record_voice_error_shows_in_state_and_page():
    chain = LiveChain(vault=MemoryVault({}))
    out = chain.record_voice_error("graph media download failed: 401")
    assert out["status"] == "error" and out["channel"] == "whatsapp"
    assert chain.state()["results"]["voice"]["error"].endswith("401")
    # El candado queda libre para el siguiente paso.
    assert chain._lock.acquire(blocking=False)
    chain._lock.release()
    html = render_live_page("en")
    assert 'r.status === "error" ? TEXT.error' in html
