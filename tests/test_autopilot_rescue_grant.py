"""RescueGrant real de M1 en la contención física del autopiloto."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from shield.autopilot import ContainmentEngine, SecurityEvent, run_pipeline
from shield.autopilot.events import (
    cold_room_physics_verdict,
    emit_safe_state_rescue,
    verify_rescue,
)
from shield.physics.contract import ColdRoomParams, ProposedAction, RoomState
from shield.physics.gate import verify_action

T0 = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)


def ev(**kw):
    kw.setdefault("ts", T0)
    return SecurityEvent.from_dict(kw)


def ola_combinada():
    evs = [
        ev(app="cold_room", actor="campaign-actor", action="defrost", target="camara",
           source="attacker", token_id="tok-campaign",
           values={"duration_min": 240, "scheduled": False}),
        ev(app="pos_erp", actor="campaign-actor", action="iban_change",
           target="supplier:acme", source="document", token_id="tok-campaign",
           ts=T0 + timedelta(minutes=2), values={"iban_last4": "9999"}),
        ev(app="payments", actor="campaign-actor", action="transfer",
           target="supplier:acme", source="document", token_id="tok-campaign",
           ts=T0 + timedelta(minutes=4), values={"amount": 9000, "beneficiary": "NEW"}),
    ]
    evs += [ev(app="ai_gateway", actor="campaign-actor", action="model_call",
               target="muse-spark-1.3", source="attacker", token_id="tok-campaign",
               ts=T0 + timedelta(minutes=5, seconds=5 * i), values={"cost_usd": 1})
            for i in range(12)]
    return evs


def test_ola_autopiloto_emite_grant_y_rescate_allow():
    engine = ContainmentEngine()
    _, result = run_pipeline(ola_combinada(), engine=engine)
    assert result.scope_level == "global"
    assert engine.safe_states.get("camara") == "last_safe_state"
    # La contención física emitió el rescate con el emisor real de M1 y
    # el gate lo dejó pasar CON grant (no por el string requested_by).
    assert engine.rescue_verdicts, "la contención no verificó ningún rescate"
    verdict = engine.rescue_verdicts[-1]
    assert verdict.decision == "allow"
    assert verdict.evidence["rescue_grant_status"] == "valid"
    assert verdict.evidence["suspicious_rescue_claim"] is False


def test_emisor_real_directo_y_grant_de_un_solo_uso():
    action, grant = emit_safe_state_rescue("camara")
    assert action.requested_by == "wairrior-autopilot"
    state = RoomState(air_c=5.5, product_c=3.8, setpoint_c=3.0)
    history = [ProposedAction(kind="defrost", duration_min=25, source="schedule",
                               requested_by="mantenimiento")]
    verdict = verify_rescue(action, grant, state=state, history=history)
    assert verdict.decision == "allow"
    assert verdict.evidence["rescue_grant_status"] == "valid"
    # El nonce es de un solo uso: reusar el mismo grant ya no da privilegio.
    again = verify_action(ColdRoomParams(), state, action, history=history,
                          rescue_grant=grant)
    assert again.evidence["rescue_grant_status"] == "reused"


def test_evento_externo_forjado_sospechoso_y_bloqueado():
    forjado = ev(app="cold_room", actor="wairrior-autopilot", action="set_setpoint",
                 target="camara", source="attacker", values={"value": 3.0})
    verdict = cold_room_physics_verdict(forjado)
    assert verdict is not None
    # El gate lo marca sospechoso: el string solo no da privilegio.
    assert verdict.evidence.get("suspicious_rescue_claim") is True
    engine = ContainmentEngine()
    _, result = run_pipeline([forjado], engine=engine)
    assert result.scope_level != "none"  # finding forged_autopilot_actor
    assert not engine.allows_write(ev(
        app="cold_room", actor="wairrior-autopilot", action="defrost",
        target="camara", source="attacker", values={"duration_min": 240}))
