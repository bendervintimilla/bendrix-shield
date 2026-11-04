"""Tests de contención M10: contain-first, circuit breaker, undo, aviso."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from shield.autopilot import ContainmentEngine, SecurityEvent, run_pipeline
from shield.autopilot.respond import dispatch_notice_sandbox

T0 = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)


def ev(**kw):
    kw.setdefault("ts", T0)
    return SecurityEvent.from_dict(kw)


def test_severidad_baja_solo_registra():
    legit = [ev(app="payments", actor="bot", action="transfer", target="supplier:old",
                values={"amount": 100, "beneficiary": "ES_OLD"})]
    _, result = run_pipeline(legit, legit)
    assert not result.circuit_breaker
    assert all(m.kind == "log" for m in result.measures)


def test_media_contiene_reversible_y_undo():
    engine = ContainmentEngine()
    ataque = [ev(app="cold_room", actor="bot", action="defrost", target="camara",
                 values={"duration_min": 60})]
    _, result = run_pipeline(ataque, engine=engine)
    assert engine.safe_states.get("camara") == "last_safe_state"
    assert result.measures and all(m.reversible for m in result.measures)
    assert engine.undo_all(result) >= 1
    assert "camara" not in engine.safe_states


def test_campana_dos_apps_no_es_global():
    engine = ContainmentEngine()
    evs = [ev(app="pos_erp", actor="bot", action="iban_change", target="supplier:acme",
              token_id="t1"),
           ev(app="payments", actor="bot", action="transfer", target="supplier:acme",
              token_id="t1", ts=T0 + timedelta(minutes=2), values={"amount": 5000})]
    _, result = run_pipeline(evs, engine=engine)
    assert result.scope_level == 'campaign' and not result.circuit_breaker
    assert result.pending_owner  # pagar / IBAN definitivo: nunca automático
    assert result.notice_en.startswith("wAIrrior stopped an attack")
    assert result.notice_es.startswith("wAIrrior detuvo un ataque")
    assert "second factor" in result.notice_en
    assert result.detect_to_contain_ms >= 0


class _FakeWhatsApp:
    simulator_mode = True

    def __init__(self):
        self.sent = []

    def send_text(self, text):
        self.sent.append(text)
        return {"simulated": True}


def test_aviso_solo_sandbox():
    _, result = run_pipeline(
        [ev(app="payments", actor="b", action="transfer", target="supplier:x",
            ts=T0.replace(hour=2), values={"amount": 99999, "beneficiary": "NEW"})])
    fake = _FakeWhatsApp()
    out = dispatch_notice_sandbox(result, fake)
    assert out["sent"] and fake.sent and "stopped an attack" in fake.sent[0]
    assert dispatch_notice_sandbox(result, None)["sent"] is False
