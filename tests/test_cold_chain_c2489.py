"""C2489-2: cadena de frío — alcance mínimo, detección y rotación 401.

Sin red ni créditos: escenario replay completo más reglas puras del
equipo (rango, horario, origen y alcance por token).
"""

from crew.refrigeracion.agent import RefrigeracionAgent, SetpointRequest, evaluate_setpoint
from crew.refrigeracion.scenario import run_scenario

COLD = ["coldchain:read", "coldchain:setpoint:camara", "coldchain:setpoint:congelador"]


def test_legit_setpoint_within_range_applies():
    agent = RefrigeracionAgent(scopes=COLD)
    out = agent.request_setpoint(SetpointRequest("camara", 3.0, hour=10))
    assert out.decision == "allow" and out.applied
    assert agent.equipment["camara"].setpoint_c == 3.0


def test_out_of_range_blocked_and_equipment_unchanged():
    agent = RefrigeracionAgent(scopes=COLD)
    out = agent.request_setpoint(SetpointRequest("congelador", 5.0, hour=12))
    assert out.decision == "block" and not out.applied
    assert any(r.startswith("out_of_range") for r in out.reasons)
    assert agent.equipment["congelador"].setpoint_c == -20.0


def test_attack_reports_range_schedule_and_origin_signals():
    out = evaluate_setpoint(
        SetpointRequest("camara", 50.0, hour=3, origin_country="BR"), scopes=COLD
    )
    assert out.decision == "block"
    assert any(r.startswith("out_of_range") for r in out.reasons)
    assert any(r.startswith("off_hours") for r in out.reasons)
    assert any(r.startswith("unexpected_origin") for r in out.reasons)


def test_single_soft_signal_asks_owner():
    out = evaluate_setpoint(SetpointRequest("camara", 3.0, hour=3), scopes=COLD)
    assert out.decision == "ask_owner" and not out.applied


def test_foreign_token_without_scope_cannot_move_setpoint():
    agent = RefrigeracionAgent(scopes=["crew"])
    out = agent.request_setpoint(SetpointRequest("camara", 3.0, hour=10))
    assert out.decision == "block" and not out.applied
    assert out.reasons == ["missing_scope:coldchain:setpoint:camara"]
    assert agent.equipment["camara"].setpoint_c == 2.0


def test_tool_names_read_and_write():
    agent = RefrigeracionAgent(scopes=COLD)
    assert agent.leer_temperatura()["decision"] == "allow"
    out = agent.fijar_setpoint(SetpointRequest("congelador", -19.0, hour=9))
    assert out.decision == "allow" and out.applied


def test_unknown_equipment_blocked():
    out = evaluate_setpoint(SetpointRequest("horno", 10.0), scopes=COLD)
    assert out.decision == "block" and out.reasons == ["unknown_equipment"]


def test_scenario_replay_attacker_401_kitchen_stays_200():
    result = run_scenario()
    assert result["ok"] is True
    assert result["network"] is False and result["credits_usd"] == 0
    s = result["statuses"]
    assert s["attacker_before"] == 200 and s["attacker_after"] == 401
    assert s["refrigeracion_after"] == s["bodega_after"] == s["compras_after"] == 200
    # Los ataques no movieron los equipos: solo cambios legítimos.
    final = {e["equipment"]: e["setpoint_c"] for e in result["final_equipment"]}
    assert final == {"camara": 3.0, "congelador": -19.0}
