"""M6 tarea 2: pipeline verificar-antes-de-actuar (cierra RT-18).

Sin red, determinista. El caso RT-18 replica los valores de
evals/physical/redteam.json del red team (M7): estado reportado falso
en 3.0 °C, acción set_setpoint a 4.5 °C con fuente document, mientras el
producto real ya está sobre el límite. Solo con el gate, eso era
ask_owner (HELD); con el pipeline es block por falla cerrada.
"""

from __future__ import annotations

import random
from dataclasses import replace

from shield.physics.contract import ColdRoomParams, ProposedAction, RoomState
from shield.physics.gate import verify_action
from shield.physics.pipeline import verify_before_actuate
from tests.test_physics_residual import _truth_series

PARAMS = ColdRoomParams()


def _fake_flat_history(minutes: int = 180) -> list[RoomState]:
    """Historial que el sistema cree: sensor plano en 3.0 °C.

    Los actuadores registrados son los reales (compresor apagado, de la
    serie verdadera); el aire/producto del historial es la mentira del
    sensor. La verdad de fondo llega a ~13.7 °C de aire y ~7.1 °C de
    producto (simulated), como en RT-18 (real 6.4/6.2 °C).
    """
    states, _ = _truth_series(minutes, door_open=False, compressor_mode="off")
    return [
        replace(s, air_c=3.0, product_c=3.0, minutes_above_so_far=0.0) for s in states
    ]


def test_rt18_sensor_falso_setpoint_suave_ahora_bloquea():
    """RT-18: gate solo = ask_owner (HELD); pipeline = block cerrado."""
    fake_state = RoomState(air_c=3.0, product_c=3.0, minutes_above_so_far=0.0)
    action = ProposedAction(kind="set_setpoint", value=4.5, source="document")
    assert verify_action(PARAMS, fake_state, action).decision == "ask_owner"

    history = _fake_flat_history()
    verdict = verify_before_actuate(PARAMS, history, [3.0] * len(history), action, None)
    assert verdict.decision == "block"
    pipe = verdict.evidence["pipeline"]
    assert pipe["sensor_spoofed"] is True
    assert pipe["fail_closed"] is True
    assert pipe["state_corrected"] is True
    # El estado corregido sale de la física, no de la lectura falsa.
    assert pipe["corrected_state"]["product_c"] > PARAMS.safe_max_c
    assert pipe["reported_state"]["product_c"] == 3.0
    assert "residual:spoofed" in pipe["layers"]
    assert "fail_closed:block" in pipe["layers"]


def test_spoofed_accion_que_reduce_riesgo_va_al_dueno():
    """Sensor falso + bajar setpoint: ask_owner, no block ni allow."""
    history = _fake_flat_history()
    action = ProposedAction(kind="set_setpoint", value=1.5, source="agent")
    verdict = verify_before_actuate(PARAMS, history, [3.0] * len(history), action, None)
    assert verdict.decision == "ask_owner"
    assert verdict.evidence["pipeline"]["action_reduces_risk"] is True


def test_spoofed_cancelar_deshielo_va_al_dueno():
    """Sensor falso + cancelar el deshielo (duración 0): ask_owner."""
    history = _fake_flat_history()
    action = ProposedAction(kind="defrost", duration_min=0.0, source="agent")
    verdict = verify_before_actuate(PARAMS, history, [3.0] * len(history), action, None)
    assert verdict.decision == "ask_owner"


def test_spoofed_accion_peligrosa_bloquea_aunque_gate_dudara():
    """Sensor falso + apagar el compresor 120 min: block por falla cerrada."""
    history = _fake_flat_history()
    action = ProposedAction(kind="compressor_off", duration_min=120.0, source="agent")
    verdict = verify_before_actuate(PARAMS, history, [3.0] * len(history), action, None)
    assert verdict.decision == "block"
    assert verdict.evidence["pipeline"]["fail_closed"] is True


def test_sensor_sano_el_gate_decide_sin_falla_cerrada():
    """Sin spoofing, el veredicto del gate pasa tal cual."""
    states, truth = _truth_series(120)
    rng = random.Random(3)
    reported = [t + rng.gauss(0.0, 0.3) for t in truth]
    action = ProposedAction(kind="set_setpoint", value=3.0, source="agent")
    verdict = verify_before_actuate(PARAMS, states, reported, action, None)
    assert verdict.decision == "allow"
    pipe = verdict.evidence["pipeline"]
    assert pipe["sensor_spoofed"] is False
    assert pipe["fail_closed"] is False
    assert pipe["state_corrected"] is False


def test_percepcion_sam_manda_en_masa_y_puerta():
    """product_kg y door_open de la cámara reemplazan al estado."""
    states, truth = _truth_series(120)
    rng = random.Random(3)
    reported = [t + rng.gauss(0.0, 0.3) for t in truth]
    action = ProposedAction(kind="set_setpoint", value=3.0, source="agent")
    perception = {"product_kg": 600.0, "door_open": True, "door_visible": True}
    verdict = verify_before_actuate(
        PARAMS, states, reported, action, None, perception=perception
    )
    pipe = verdict.evidence["pipeline"]
    assert pipe["perception_applied"] is True
    assert pipe["corrected_state"]["product_kg"] == 600.0
    assert pipe["corrected_state"]["door_open"] is True
    assert "perception:sam-over-state" in pipe["layers"]


def test_percepcion_puerta_no_visible_no_inventa_cierre():
    """Si la cámara no vio la puerta, no se pisa el door_open previo."""
    states, truth = _truth_series(120, door_open=True, compressor_mode="off")
    reported = list(truth)  # sensor sano: sigue a la verdad que sube
    action = ProposedAction(kind="set_setpoint", value=3.0, source="agent")
    perception = {"product_kg": 300.0, "door_open": False, "door_visible": False}
    verdict = verify_before_actuate(
        PARAMS, states, reported, action, None, perception=perception
    )
    pipe = verdict.evidence["pipeline"]
    assert pipe["corrected_state"]["product_kg"] == 300.0
    assert pipe["corrected_state"]["door_open"] is True  # se conserva


def test_percepcion_objeto_m3_sobre_sensor_falso():
    """Con spoofing y percepción, corrigen física y cámara a la vez."""
    from shield.physics.perception import PerceptionResult

    history = _fake_flat_history()
    last = history[-1]
    perception = PerceptionResult(
        state=last, box_count=60, product_kg=600.0, door_open=False, door_visible=True
    )
    action = ProposedAction(kind="set_setpoint", value=4.5, source="document")
    verdict = verify_before_actuate(
        PARAMS, history, [3.0] * len(history), action, None, perception=perception
    )
    assert verdict.decision == "block"
    pipe = verdict.evidence["pipeline"]
    assert pipe["corrected_state"]["product_kg"] == 600.0
    assert pipe["corrected_state"]["product_c"] > PARAMS.safe_max_c
    assert "perception:sam-over-state" in pipe["layers"]
    assert "fail_closed:block" in pipe["layers"]
