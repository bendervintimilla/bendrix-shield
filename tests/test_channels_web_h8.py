"""H8: WhatsApp, voz, panel y E2E guardián → runbook → atacante 401."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime

import httpx
from fastapi.testclient import TestClient

from channels.approvals import ApprovalBroker, ChannelApprover
from channels.voice import (
    VoiceApprovalFlow,
    VoiceApprover,
    interpret_with_spark,
    parse_voice_command,
    transcribe_audio,
)
from channels.whatsapp import (
    WhatsAppChannel,
    WhatsAppConfig,
    load_config,
    simulated_click_payload,
    verify_signature,
)
from sandbox.attacker import attempt_statuses, format_timeline
from shield.actions import Actions
from shield.agent import GuardianAgent, RunbookGuardianActions
from shield.gateway.app import UPSTREAM_KEY_NAME, create_app
from shield.meta_client import NeedsCredits
from shield.registry import Registry
from shield.schemas import CallLog
from shield.sdk.token_store import InMemoryTokenStore
from shield.vault import MemoryVault
from web.app import build_replay_state, create_panel_app

SECRET = "app-secret-de-prueba"


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def _broker_with_plan(targets=("bodega",)):
    broker = ApprovalBroker()
    plan = {
        "summary": "rotar tokens",
        "steps": [
            {"action": "rotate_token", "target": t, "reason": "anomalía", "requires_approval": True}
            for t in targets
        ]
        + [
            {
                "action": "verify",
                "target": targets[0],
                "reason": "salud",
                "requires_approval": False,
            }
        ],
    }
    req = broker.request(plan)
    return broker, req.approval_id


# -- WhatsApp ---------------------------------------------------------------


def test_whatsapp_signature_and_verification_get():
    body = b'{"entry":[]}'
    assert verify_signature(body, _sign(body), SECRET)
    assert not verify_signature(body, _sign(b"otro"), SECRET)
    assert not verify_signature(body, None, SECRET)

    broker, approval_id = _broker_with_plan()
    channel = WhatsAppChannel(
        broker, config=WhatsAppConfig(verify_token="tok-verifica", app_secret=SECRET)
    )
    app = create_panel_app(build_replay_state())
    # El GET de verificación vive en el router del panel; probamos el canal y la ruta.
    assert channel.verify_challenge("subscribe", "tok-verifica", "12345") == "12345"
    assert channel.verify_challenge("subscribe", "malo", "12345") is None
    client = TestClient(app)
    ok = client.get(
        "/webhook/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "shield-demo-verify",
            "hub.challenge": "777",
        },
    )
    assert ok.status_code == 200 and ok.text == "777"
    assert approval_id.startswith("pend_")


def test_whatsapp_buttons_idempotent_and_reject_blocks():
    import json

    broker, approval_id = _broker_with_plan()
    channel = WhatsAppChannel(broker, config=WhatsAppConfig(app_secret=SECRET))
    app = create_panel_app(build_replay_state())
    app.state.whatsapp = channel
    # Montamos el canal de prueba sobre un broker propio vía handle_payload directo
    # y también por HTTP con firma sobre el broker del panel.
    payload = simulated_click_payload(approval_id=approval_id, action="approve", message_id="m-1")
    first = channel.handle_payload(payload)
    second = channel.handle_payload(payload)
    assert first[0]["status"] == "approved"
    assert second[0]["status"] == "duplicate"
    assert broker.is_approved(approval_id)

    broker2, approval2 = _broker_with_plan()
    channel2 = WhatsAppChannel(broker2, config=WhatsAppConfig(app_secret=SECRET))
    rejected = channel2.handle_payload(
        simulated_click_payload(approval_id=approval2, action="reject", message_id="m-2")
    )
    assert rejected[0]["status"] == "rejected" and broker2.is_rejected(approval2)

    detail = channel2.handle_payload(
        simulated_click_payload(approval_id=approval2, action="detail", message_id="m-3")
    )
    assert detail[0]["status"] == "detail_sent" and channel2.outbox

    # POST firmado: firma mala → 403; firma buena sobre el panel → 200.
    client = TestClient(app)
    raw = json.dumps(
        simulated_click_payload(approval_id="pend_x", action="approve", message_id="m-9")
    ).encode()
    bad = client.post(
        "/webhook/whatsapp", content=raw, headers={"x-hub-signature-256": "sha256=00"}
    )
    # El panel de replay no tiene app_secret: acepta en simulador. Solo exigimos
    # que el verificador puro rechace la firma mala (cubierto arriba).
    assert bad.status_code in (200, 403)
    signed_app_broker, signed_id = _broker_with_plan()
    signed_channel = WhatsAppChannel(signed_app_broker, config=WhatsAppConfig(app_secret=SECRET))
    from fastapi import FastAPI

    from channels.whatsapp import create_router

    signed_app = FastAPI()
    signed_app.include_router(create_router(signed_channel))
    signed_client = TestClient(signed_app, raise_server_exceptions=False)
    raw2 = json.dumps(
        simulated_click_payload(approval_id=signed_id, action="approve", message_id="m-10")
    ).encode()
    assert (
        signed_client.post(
            "/webhook/whatsapp", content=raw2, headers={"x-hub-signature-256": "sha256=00"}
        ).status_code
        == 403
    )
    good = signed_client.post(
        "/webhook/whatsapp", content=raw2, headers={"x-hub-signature-256": _sign(raw2)}
    )
    assert good.status_code == 200 and good.json()["results"][0]["status"] == "approved"


def test_whatsapp_config_from_vault_and_simulator_outbox():
    vault = MemoryVault(
        {"whatsapp-test-phone": "593991112233", "whatsapp-test-token": "token-de-prueba"}
    )
    config = load_config(vault)
    assert config.phone_number == "593991112233" and config.token == "token-de-prueba"
    assert not config.live  # sin phone_number_id: simulador

    broker, approval_id = _broker_with_plan()
    channel = WhatsAppChannel(broker)
    assert channel.simulator_mode
    sent = channel.send_approval_request(approval_id, "¿Roto el token de bodega?")
    assert sent["simulated"] is True
    buttons = sent["payload"]["interactive"]["action"]["buttons"]
    assert [b["reply"]["title"] for b in buttons] == ["Aprobar", "Rechazar", "Ver detalle"]
    assert "token-de-prueba" not in str(sent)


# -- Voz --------------------------------------------------------------------


def test_voice_parse_partial_and_reject():
    full = parse_voice_command("sí, rota todo")
    assert full.action == "approve" and not full.is_partial
    partial = parse_voice_command("sí, rota todo menos Stripe")
    assert partial.action == "approve" and partial.exclude_targets == ["stripe"]
    only = parse_voice_command("rota solo bodega por favor")
    assert only.only_targets == ["bodega"]
    assert parse_voice_command("no, rechaza eso").action == "reject"
    assert parse_voice_command("cuéntame un chiste").action == "unknown"


class _NoCreditsClient:
    def chat_completions(self, **kwargs):
        raise NeedsCredits(402, "billing")

    def transcribe_file(self, path):
        raise NeedsCredits(402, "billing")


def test_voice_spark_fallback_and_transcribe_needs_credits():
    intent = interpret_with_spark("sí, rota todo menos stripe", _NoCreditsClient())
    assert intent.source == "deterministic" and intent.exclude_targets == ["stripe"]
    heard = transcribe_audio("nota.wav", _NoCreditsClient())
    assert heard["needs_credits"] is True and heard["transcript"] == ""


def test_voice_partial_requires_confirmation_then_approves_subset():
    broker, approval_id = _broker_with_plan(targets=("bodega", "stripe"))
    flow = VoiceApprovalFlow(broker)
    first = flow.handle_transcript(approval_id, "sí, rota todo menos Stripe")
    assert first["status"] == "confirmation_required"
    assert not broker.is_approved(approval_id)
    done = flow.confirm(approval_id)
    assert done["status"] == "approved"
    assert broker.approved_steps_for(approval_id) == {("rotate_token", "bodega")}


# -- E2E: guardián → ask_owner (WhatsApp) → runbook H6 → verify → 401 -------


def _ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-1",
            "model": "muse-spark-1.3",
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 4},
        },
    )


def _logs(agent: str, country: str, model: str, cost: float) -> list[CallLog]:
    return [
        CallLog(
            ts=datetime(2026, 10, 28, 8 + i, tzinfo=UTC),
            agent=agent,
            model=model,
            cost_usd=cost,
            src_country=country,
        )
        for i in range(3)
    ]


def _build_guardian_world():
    registry = Registry(":memory:")
    broker = ApprovalBroker()
    gateway = TestClient(
        create_app(
            registry=registry,
            vault=MemoryVault({UPSTREAM_KEY_NAME: "upstream-key-0000"}),
            upstream_transport=httpx.MockTransport(_ok_handler),
            sandbox=True,
        )
    )
    store = InMemoryTokenStore()
    bodega, bodega_raw = registry.create_token("bodega", "crew")
    compras, compras_raw = registry.create_token("compras", "crew")
    store.set_token("bodega", bodega_raw, bodega.token_id)
    actions = Actions(registry=registry, token_store=store, approvals=broker.registry, sandbox=True)
    approver = ChannelApprover(broker)
    guardian = GuardianAgent(
        logs=_logs("bodega", "BR", "muse-spark-1.3", 18.0),
        baseline=_logs("bodega", "EC", "sam-3.1", 1.0),
        actions=RunbookGuardianActions(actions, grace_s=0.0),
        approver=approver,
    )
    return registry, broker, gateway, store, guardian, bodega, bodega_raw, compras_raw


def _post(gateway, raw):
    return gateway.post(
        "/v1/chat/completions",
        json={"model": "muse-spark-1.3", "messages": [{"role": "user", "content": "cuenta"}]},
        headers={"Authorization": f"Bearer {raw}"},
    )


def test_e2e_guardian_whatsapp_runbook_attacker_401():
    registry, broker, gateway, store, guardian, bodega, bodega_raw, compras_raw = (
        _build_guardian_world()
    )
    channel = WhatsAppChannel(broker)
    assert _post(gateway, bodega_raw).status_code == 200  # atacante aún entra

    guardian.tool_match_exposure()
    guardian.tool_detect_anomaly()
    guardian.tool_propose_plan()
    asked = guardian.tool_ask_owner()
    approval_id = asked["pending_approval_id"]
    assert approval_id and not asked["approved"]
    sent = channel.send_approval_request(approval_id, "Token de bodega usado desde Brasil. ¿Roto?")
    assert sent["simulated"] is True

    # Sin aprobación, el runbook no se ejecuta ni por la vía directa.
    blocked = guardian.dispatch("rotate_token", {"agent": "bodega", "approval_id": approval_id})
    assert blocked["status"] == "blocked"

    clicked = channel.handle_payload(
        simulated_click_payload(approval_id=approval_id, action="approve", message_id="wamid-1")
    )
    assert clicked[0]["status"] == "approved"
    # Idempotente: repetir el mismo mensaje no re-aprueba ni rompe nada.
    again = channel.handle_payload(
        simulated_click_payload(approval_id=approval_id, action="approve", message_id="wamid-1")
    )
    assert again[0]["status"] == "duplicate"

    report = guardian.execute_approved(approval_id)
    assert any(
        e["action"] == "rotate_token" and e.get("status") == "applied" and e.get("verify_ok")
        for e in report.executed
    ), report.executed
    assert any(e["action"] == "verify" for e in report.executed)

    statuses = attempt_statuses(gateway, bodega_raw, attempts=2)
    assert statuses == [401, 401]
    assert format_timeline([200, *statuses]) == "200 → 401 → 401"
    assert _post(gateway, store.get_token("bodega")).status_code == 200
    assert _post(gateway, compras_raw).status_code == 200
    assert registry.get_token(bodega.token_id).status.value == "revoked"  # gracia 0 del runbook H6


def test_e2e_voice_partial_only_rotates_approved_agent():
    registry = Registry(":memory:")
    broker = ApprovalBroker()
    store = InMemoryTokenStore()
    bodega, bodega_raw = registry.create_token("bodega", "crew")
    compras, compras_raw = registry.create_token("compras", "crew")
    store.set_token("bodega", bodega_raw, bodega.token_id)
    actions = Actions(registry=registry, token_store=store, approvals=broker.registry, sandbox=True)
    approver = VoiceApprover(broker, "sí, rota todo menos compras", confirmed=True)
    guardian = GuardianAgent(
        logs=_logs("bodega", "BR", "muse-spark-1.3", 18.0)
        + _logs("compras", "BR", "muse-spark-1.3", 18.0),
        baseline=_logs("bodega", "EC", "sam-3.1", 1.0)
        + _logs("compras", "EC", "muse-spark-1.3", 1.0),
        actions=RunbookGuardianActions(actions, grace_s=0.0),
        approver=approver,
    )
    report = guardian.run_once()
    assert report.approval_id
    by_target = {e["target"]: e for e in report.executed if e["action"] == "rotate_token"}
    assert by_target["bodega"]["status"] == "applied"
    assert by_target["compras"]["status"] == "skipped"
    assert registry.get_token(bodega.token_id).status.value == "revoked"  # gracia 0 del runbook H6
    assert registry.get_token(compras.token_id).status.value == "active"


# -- Panel ------------------------------------------------------------------


def test_panel_replay_approve_executes_and_attacker_401():
    state = build_replay_state()
    client = TestClient(create_panel_app(state))
    home = client.get("/")
    assert home.status_code == 200
    for needle in ("bodega", "compras", "Attacker", "clock", "Approve"):
        assert needle in home.text, needle

    before = client.get("/panel/state").json()
    assert before["attacker_timeline"].startswith("200")
    assert len(before["pending"]) == 1
    approval_id = before["pending"][0]["approval_id"]

    approved = client.post(f"/panel/approve/{approval_id}")
    assert approved.status_code == 200
    after = client.get("/panel/state").json()
    assert after["pending"] == []
    assert any(e.get("status") == "applied" for e in after["executed"])
    assert after["attacker_statuses"][-1] == 401

    probe = client.post("/panel/attacker/probe")
    assert probe.status_code == 200 and "401" in probe.text


def test_panel_lang_es_shows_aprobar_and_cookie_keeps_it():
    client = TestClient(create_panel_app(build_replay_state()))
    spanish = client.get("/?lang=es")
    assert spanish.status_code == 200
    assert "Aprobar" in spanish.text
    assert "Alguien está usando el token robado de Bodega." in spanish.text
    # La cookie guarda el idioma para la siguiente visita sin parámetro.
    again = client.get("/")
    assert "Aprobar" in again.text


def test_panel_voice_partial_confirmation_flow():
    broker, approval_id = _broker_with_plan(targets=("bodega", "stripe"))
    flow = VoiceApprovalFlow(broker)
    outcome = flow.handle_transcript(approval_id, "sí, rota todo menos Stripe", confirmed=False)
    assert outcome["status"] == "confirmation_required"
    assert not broker.is_approved(approval_id)
    confirmed = flow.confirm(approval_id)
    assert confirmed["status"] == "approved"
    assert broker.approved_steps_for(approval_id) == {("rotate_token", "bodega")}
