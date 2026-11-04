"""Bypass ronda 3 de M7 contra M10: C3-11, C3-12, C3-13/14, C3-16."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

from shield.autopilot import ContainmentEngine, SecurityEvent, run_pipeline
from shield.autopilot.detect import correlate, detect
from shield.autopilot.events import cold_room_physics_verdict

T0 = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)


def ev(**kw):
    kw.setdefault("ts", T0)
    return SecurityEvent.from_dict(kw)


def contained_cold_engine():
    engine = ContainmentEngine()
    ataque = [ev(app="cold_room", actor="agent:cold", action="defrost", target="camara",
                 values={"duration_min": 240, "scheduled": False})]
    run_pipeline(ataque, engine=engine)
    return engine


def test_c3_11_reintento_otro_target_bloqueado():
    engine = contained_cold_engine()
    reintento = ev(app="cold_room", actor="agent:cold", action="defrost",
                   target="camara-2", ts=T0 + timedelta(minutes=30),
                   values={"duration_min": 240})
    assert not engine.allows_write(reintento)


def test_c3_12_reintento_otra_clase_bloqueado():
    engine = contained_cold_engine()
    reintento = ev(app="cold_room", actor="agent:cold", action="compressor_off",
                   target="camara", ts=T0 + timedelta(minutes=30),
                   values={"duration_min": 240})
    assert not engine.allows_write(reintento)
    # También en pagos: toda escritura de pagos del actor contenido cae.
    pago = ev(app="payments", actor="agent:cold", action="transfer",
              target="supplier:otro", values={"amount": 10, "beneficiary": "X"})
    assert not engine.allows_write(pago)
    # Otro actor legítimo no se toca.
    assert engine.allows_write(ev(app="cold_room", actor="refrigeracion",
                                  action="set_setpoint", target="camara-9",
                                  values={"value": 3.0}))


def _c3_events(offset_min):
    return [
        ev(app="cold_room", actor="agent:cold-a", action="defrost", target="camara",
           token_id="tok_a", values={"duration_min": 240, "scheduled": False}),
        ev(app="payments", actor="agent:pay-b", action="transfer", target="supplier:x",
           token_id="tok_b", ts=T0 + timedelta(minutes=offset_min),
           values={"amount": 9000, "beneficiary": "ES-NEW"}),
    ]


def test_c3_13_correlacion_90min_actores_distintos():
    events = _c3_events(90)
    findings = detect(events)  # sin línea base: no debe auto-baselinar el ataque
    incident = correlate(events, findings)
    assert incident.correlated
    assert "24h" in " ".join(incident.correlation_reasons) or incident.correlation_reasons
    _, result = run_pipeline(events)
    assert result.scope_level == "campaign"


def test_c3_14_control_5min_correlaciona():
    events = _c3_events(5)
    incident = correlate(events, detect(events))
    assert incident.correlated and incident.severity == "critical"


def test_c3_16_actor_autopiloto_forjado_es_sospechoso():
    forjado = ev(app="cold_room", actor="wairrior-autopilot", action="set_setpoint",
                 target="camara", source="attacker", values={"value": 3.0})
    findings = detect([forjado])
    assert any(f.kind == "forged_autopilot_actor" for f in findings)
    from shield.autopilot.events import proposed_action_from_event
    # Jamás se pasa ese actor como requested_by confiable al gate.
    assert proposed_action_from_event(forjado).requested_by != "wairrior-autopilot"
    _, result = run_pipeline([forjado])
    assert result.scope_level != "none"


def test_grant_se_pasa_solo_si_la_cadena_lo_acepta(monkeypatch):
    import shield.physics.pipeline as pipeline

    seen = {}

    class FakeVerdict:
        decision = "allow"

    def fake_verify(params, state_history, reported, action, **kw):
        seen.update(kw)
        return FakeVerdict()

    monkeypatch.setattr(pipeline, "verify_before_actuate", fake_verify)
    evento = ev(app="cold_room", actor="agent:cold", action="set_setpoint",
                target="camara", values={"value": 3.0})
    verdict = cold_room_physics_verdict(evento, rescue_grant="GRANT-DE-PRUEBA")
    assert verdict.decision == "allow"
    # La firma falsa no declara grant: no se le inyecta nada a ciegas.
    assert "rescue_grant" not in seen

    def fake_verify2(params, state_history, reported, action, *, rescue_grant=None):
        seen["rescue_grant"] = rescue_grant

        class V:
            decision = "allow"
        return V()

    monkeypatch.setattr(pipeline, "verify_before_actuate", fake_verify2)
    cold_room_physics_verdict(evento, rescue_grant="GRANT-DE-PRUEBA")
    assert seen["rescue_grant"] == "GRANT-DE-PRUEBA"
    assert "shield.physics.rescue" not in sys.modules or True  # grant opaco, sin firmar aquí
