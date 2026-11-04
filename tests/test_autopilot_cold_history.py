"""Residuos M7: grant por el pipeline M6 e historia por equipo (24 h)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from shield.autopilot import SecurityEvent, run_pipeline
from shield.autopilot.detect import detect
from shield.autopilot.events import (
    ColdRoomHistory,
    cold_room_physics_verdict,
    emit_safe_state_rescue,
)

T0 = datetime(2026, 11, 4, 6, 0, tzinfo=UTC)


def ev(**kw):
    kw.setdefault("ts", T0)
    return SecurityEvent.from_dict(kw)


def defrost(offset_h, duration=40):
    return ev(app="cold_room", actor="agent:cold", action="defrost", target="camara",
              source="schedule", ts=T0 + timedelta(hours=offset_h),
              values={"duration_min": duration, "scheduled": True})


def test_deshielos_lentos_repetidos_se_acumulan_defrost_pattern():
    # Caso M7 C3-15 repetido: 4 deshielos "programados" de 40 min en 24 h.
    events = [defrost(0), defrost(6), defrost(12), defrost(18)]
    findings = detect(events)
    assert any(f.kind == "defrost_pattern" for f in findings)


def test_un_solo_deshielo_programado_no_es_patron():
    findings = detect([defrost(0)])
    assert not any(f.kind == "defrost_pattern" for f in findings)
    assert not any(f.kind == "defrost_anomaly" for f in findings)


def test_historia_persiste_entre_llamadas_con_el_mismo_tracker():
    tracker = ColdRoomHistory()
    run_pipeline([defrost(0), defrost(6)], cold_history=tracker)
    assert len(tracker.recent_actions("camara", T0 + timedelta(hours=6))) == 2
    # Una tercera llamada, horas después, ve la historia acumulada.
    _, result = run_pipeline([defrost(12), defrost(18)], cold_history=tracker)
    assert result.scope_level != "none"


def test_grant_pasa_por_la_cadena_con_pipeline():
    action, grant = emit_safe_state_rescue("camara")
    evento_rescate = ev(app="cold_room", actor="wairrior-autopilot",
                        action="set_setpoint", target="camara",
                        source="schedule", values={"value": action.value})
    verdict = cold_room_physics_verdict(evento_rescate, rescue_grant=grant)
    assert verdict is not None
    assert verdict.evidence.get("rescue_grant_status") == "valid"
    assert verdict.decision == "allow"
