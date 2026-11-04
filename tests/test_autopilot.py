"""Tests deterministas de M10 (sin red): eventos, detección y correlación."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from shield.autopilot import (
    SecurityEvent,
    correlate,
    detect,
    from_cold_room,
    from_gateway_call,
    from_payment,
    from_pos_erp,
    from_webhook,
    run_pipeline,
)

T0 = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)


def ev(**kw):
    kw.setdefault("ts", T0)
    return SecurityEvent.from_dict(kw)


def test_webhook_y_adaptadores():
    e = from_webhook({"app": "payments", "actor": "a", "action": "transfer",
                      "target": "supplier:x", "ts": T0.isoformat(),
                      "values": {"amount": 10}})
    assert e.app == "payments" and e.values["amount"] == 10
    assert from_payment({"actor": "a", "action": "transfer", "amount": 5}).app == "payments"
    assert from_pos_erp({"actor": "a", "supplier": "s"}).app == "pos_erp"
    assert from_cold_room({"kind": "defrost", "duration_min": 30}).action == "defrost"
    gw = from_gateway_call({"agent": "bot", "model": "m", "ts": T0, "cost_usd": 1})
    assert gw.app == "ai_gateway" and gw.actor == "bot"
    assert SecurityEvent.from_dict(e.to_dict()).event_id == e.event_id


def test_beneficiario_nuevo_monto_horario():
    base = [ev(app="payments", actor="bot", action="transfer", target="supplier:old",
               ts=T0, values={"amount": 100, "beneficiary": "ES_OLD"})]
    ataque = ev(app="payments", actor="bot", action="transfer", target="supplier:new",
                ts=T0.replace(hour=3), values={"amount": 9000, "beneficiary": "ES_NEW"})
    findings = detect([ataque], base)
    assert findings and findings[0].severity in ("high", "medium")
    legit = ev(app="payments", actor="bot", action="transfer", target="supplier:old",
               ts=T0.replace(hour=10), values={"amount": 110, "beneficiary": "ES_OLD"})
    assert not detect([legit], base)


def test_iban_seguido_de_pago_es_critico():
    evs = [ev(app="pos_erp", actor="bot", action="iban_change", target="supplier:acme", ts=T0),
           ev(app="payments", actor="bot", action="transfer", target="supplier:acme",
              ts=T0 + timedelta(hours=1), values={"amount": 500})]
    findings = detect(evs)
    assert any(f.kind == "iban_then_payment" and f.severity == "critical" for f in findings)


def test_deshielo_fuera_de_calendario_y_fisica():
    largo = from_cold_room({"action": "defrost", "duration_min": 240, "ts": T0,
                            "actor": "attacker", "source": "attacker"})
    findings = detect([largo])
    assert any(f.kind in ("defrost_anomaly", "physics_block") for f in findings)
    programado = from_cold_room({"action": "defrost", "duration_min": 20, "scheduled": True,
                                 "ts": T0})
    assert not [f for f in detect([programado], [programado])
                if f.kind == "defrost_anomaly"]


def test_rafaga_token_y_correlacion_dos_apps():
    evs = [ev(app="ai_gateway", actor="bot", action="model_call", token_id="tok1",
              ts=T0 + timedelta(seconds=i)) for i in range(12)]
    evs.append(ev(app="payments", actor="bot", action="transfer", target="supplier:x",
                  token_id="tok1", ts=T0 + timedelta(seconds=5),
                  values={"amount": 99999, "beneficiary": "NEW"}))
    findings = detect(evs)
    assert any(f.kind == "token_burst" for f in findings)
    incident = correlate(evs, findings)
    assert incident.correlated and incident.severity == "critical"
    assert len(incident.apps) >= 2


def test_triage_no_decide_contencion():
    evs = [ev(app="payments", actor="bot", action="transfer", target="supplier:x",
              ts=T0.replace(hour=2), values={"amount": 99999, "beneficiary": "NEW"})]
    incident, result = run_pipeline(evs, spark=lambda i: "parece malo")
    assert incident.triage == "parece malo"
    # La contención sale de las reglas aunque el triage no exista.
    _, result_sin = run_pipeline(evs)
    assert result.measures and result_sin.measures
    assert result.circuit_breaker == result_sin.circuit_breaker
