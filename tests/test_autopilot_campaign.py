"""Nivel campaign, global restringido y aviso de negocio (revisión 2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from shield.autopilot import ContainmentEngine, SecurityEvent, run_pipeline

T0 = datetime(2026, 11, 4, 3, 12, tzinfo=UTC)
BANNED = ("block_action", "circuit_breaker", "tok-", "evt_", "`", "M1", "freeze_app")


def ev(**kw):
    kw.setdefault("ts", T0)
    return SecurityEvent.from_dict(kw)


def arkea_events():
    return [
        ev(app="pos_erp", actor="payments-bot", action="iban_change",
           target="supplier:acme", token_id="tok-pay",
           ts=T0, values={"iban_last4": "9999"}),
        ev(app="payments", actor="payments-bot", action="transfer",
           target="supplier:acme", token_id="tok-pay", ts=T0 + timedelta(minutes=5),
           values={"amount": 8000, "beneficiary": "NEW"}),
    ]


def test_arkea_es_campaign_no_global_y_recurrentes_viven():
    engine = ContainmentEngine()
    _, result = run_pipeline(arkea_events(), engine=engine)
    assert result.scope_level == "campaign"
    assert not result.circuit_breaker
    # Pago recurrente del MISMO bot a beneficiario conocido sigue.
    assert engine.allows_write(ev(
        app="payments", actor="payments-bot", action="transfer",
        target="supplier:known", source="human",
        values={"amount": 500, "beneficiary": "KNOWN", "beneficiary_known": True}))
    # Transferencia a beneficiario nuevo y el proveedor afectado quedan congelados.
    assert not engine.allows_write(ev(
        app="payments", actor="payments-bot", action="transfer",
        target="supplier:otro", values={"amount": 100, "beneficiary": "OTRO"}))
    assert not engine.allows_write(ev(
        app="pos_erp", actor="payments-bot", action="iban_change",
        target="supplier:acme", values={"iban_last4": "1111"}))
    # Otras apps intactas.
    assert engine.allows_write(ev(app="cold_room", actor="refrigeracion",
                                  action="set_setpoint", target="camara",
                                  values={"value": 3.0}))


def test_global_solo_tres_apps_y_humanas_recurrentes_viven():
    engine = ContainmentEngine()
    evs = arkea_events() + [
        ev(app="cold_room", actor="payments-bot", action="defrost", target="camara",
           token_id="tok-pay", source="attacker", ts=T0 + timedelta(minutes=2),
           values={"duration_min": 240}),
    ]
    _, result = run_pipeline(evs, engine=engine)
    assert result.scope_level == "global" and result.circuit_breaker
    # Humana recurrente a beneficiario conocido sigue aun en global.
    assert engine.allows_write(ev(
        app="payments", actor="dueno", action="transfer", target="supplier:known",
        source="human", values={"amount": 500, "beneficiary_known": True}))
    # Escritura de agente no recurrente queda pausada.
    assert not engine.allows_write(ev(
        app="payments", actor="payments-bot", action="transfer",
        target="supplier:known", source="agent",
        values={"amount": 500, "beneficiary_known": True}))


def test_aviso_negocio_corto_sin_ids():
    _, result = run_pipeline(arkea_events(), engine=ContainmentEngine())
    for notice in (result.notice_en, result.notice_es):
        assert len([ln for ln in notice.splitlines() if ln.strip()]) <= 7
        for banned in BANNED:
            assert banned not in notice
    assert result.notice_en.startswith("wAIrrior stopped an attack at 03:12.")
    assert "Tap to undo" in result.notice_en
    assert "second factor" in result.notice_en
