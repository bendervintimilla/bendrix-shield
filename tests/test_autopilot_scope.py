"""Alcance del circuit breaker en 3 niveles (revisión del orquestador)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from shield.autopilot import ContainmentEngine, SecurityEvent, run_pipeline

T0 = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)


def ev(**kw):
    kw.setdefault("ts", T0)
    return SecurityEvent.from_dict(kw)


def legit_payments():
    return ev(app="payments", actor="payments-bot", action="transfer",
              target="supplier:known", values={"amount": 500, "beneficiary": "KNOWN",
                                               "beneficiary_known": True})


def test_critico_una_sola_app_no_congela_las_otras():
    engine = ContainmentEngine()
    ataque = [ev(app="cold_room", actor="attacker", action="defrost", target="camara",
                 source="attacker", values={"duration_min": 240})]
    _, result = run_pipeline(ataque, engine=engine)
    assert result.scope_level == "app"
    assert not result.circuit_breaker
    # Otras apps intactas; otro equipo también; solo el deshielo de esa cámara cae.
    assert engine.allows_write(legit_payments())
    assert engine.allows_write(ev(app="cold_room", actor="refrigeracion",
                                  action="set_setpoint", target="camara-2",
                                  values={"value": 3.0}))
    assert not engine.allows_write(ev(app="cold_room", actor="attacker",
                                      action="defrost", target="camara",
                                      values={"duration_min": 240}))


def test_nivel_app_solo_ese_tipo_de_operacion():
    engine = ContainmentEngine()
    ataque = [ev(app="payments", actor="payments-bot", action="transfer",
                 target="supplier:new", ts=T0.replace(hour=3),
                 values={"amount": 9000, "beneficiary": "NEW"})]
    base = [ev(app="payments", actor="payments-bot", action="transfer",
               target="supplier:known", ts=T0.replace(hour=10),
               values={"amount": 500, "beneficiary": "KNOWN"})]
    _, result = run_pipeline(ataque, base, engine=engine)
    assert result.scope_level in ("actor", "app")
    assert not result.circuit_breaker
    # Pago recurrente a beneficiario conocido sigue; a beneficiario nuevo, no.
    assert engine.allows_write(legit_payments())
    assert not engine.allows_write(ev(app="payments", actor="payments-bot",
                                      action="transfer", target="supplier:otro",
                                      values={"amount": 100, "beneficiary": "OTRO"}))
    assert engine.allows_write(ev(app="cold_room", actor="refrigeracion",
                                  action="set_setpoint", target="camara",
                                  values={"value": 3.0}))


def test_global_solo_con_correlacion_dos_apps():
    engine = ContainmentEngine()
    evs = [
        ev(app="cold_room", actor="campaign", action="defrost", target="camara",
           token_id="tok-c", source="attacker", values={"duration_min": 240}),
        ev(app="payments", actor="campaign", action="transfer", target="supplier:acme",
           token_id="tok-c", ts=T0 + timedelta(minutes=3),
           values={"amount": 9000, "beneficiary": "NEW"}),
        ev(app="pos_erp", actor="campaign", action="iban_change", target="supplier:acme",
           token_id="tok-c", ts=T0 + timedelta(minutes=1), values={"iban_last4": "9999"}),
    ]
    _, result = run_pipeline(evs, engine=engine)
    assert result.scope_level == "global" and result.circuit_breaker
    assert not engine.allows_write(legit_payments())
    # El aviso completo nombra lo hecho y lo pendiente del dueño.
    assert "circuit_breaker" in result.notice_en
    assert "second factor" in result.notice_en
