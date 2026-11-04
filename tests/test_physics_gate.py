"""Tests deterministas del escudo predictivo físico (sin red)."""

from __future__ import annotations

import time

from shield.physics.contract import ColdRoomParams, ProposedAction, RoomState
from shield.physics.gate import verify_action

PARAMS = ColdRoomParams()


def test_compressor_off_6h_is_blocked() -> None:
    """Apagado largo: block, con ruptura predicha y evidencia legible."""
    verdict = verify_action(
        PARAMS, RoomState(), ProposedAction(kind="compressor_off", duration_min=360)
    )
    assert verdict.decision == "block"
    assert verdict.predicted_breach_min is not None
    assert verdict.peak_product_c > PARAMS.safe_max_c
    assert verdict.minutes_above_limit > PARAMS.max_minutes_above
    assert verdict.evidence["simulated"] is True
    assert "°C" in verdict.evidence["summary"]


def test_slow_setpoint_drift_in_history_is_blocked() -> None:
    """Cinco setpoints +0.8 °C (cada uno en 0–4 °C) suman una deriva: block."""
    state = RoomState(air_c=0.0, product_c=0.0, setpoint_c=0.0)
    history = [
        ProposedAction(kind="set_setpoint", value=value, start_in_min=10 * i)
        for i, value in enumerate([0.8, 1.6, 2.4, 3.2])
    ]
    action = ProposedAction(kind="set_setpoint", value=4.0, start_in_min=40)
    verdict = verify_action(PARAMS, state, action, history=history)
    assert verdict.decision == "block"
    assert verdict.evidence["cumulative_setpoint_drift_c"] == 4.0
    assert verdict.evidence["setpoint_steps"] == 5


def test_setpoint_4_is_allowed_with_margin_informed() -> None:
    """Setpoint 4.0 °C (en rango): allow, con el margen en la evidencia."""
    verdict = verify_action(PARAMS, RoomState(), ProposedAction(kind="set_setpoint", value=4.0))
    assert verdict.decision == "allow"
    assert verdict.peak_product_c < PARAMS.safe_max_c
    assert verdict.evidence["margin_to_safe_max_c"] > 1.0


def test_setpoint_very_close_to_limit_asks_owner() -> None:
    """Un setpoint destino a ≤0.5 °C del límite sí escala al dueño."""
    verdict = verify_action(PARAMS, RoomState(), ProposedAction(kind="set_setpoint", value=4.6))
    assert verdict.decision == "ask_owner"
    assert verdict.peak_product_c < PARAMS.safe_max_c


def test_defrost_20min_is_allowed() -> None:
    """Deshielo legítimo de 20 min: allow."""
    verdict = verify_action(PARAMS, RoomState(), ProposedAction(kind="defrost", duration_min=20))
    assert verdict.decision == "allow"
    assert verdict.peak_product_c < PARAMS.safe_max_c - 1.0


def test_cold_load_30kg_is_allowed() -> None:
    """Carga de 30 kg en una cámara con 1000 kg fríos: allow."""
    state = RoomState(product_kg=1000.0)
    verdict = verify_action(PARAMS, state, ProposedAction(kind="load_product", value=30.0))
    assert verdict.decision == "allow"
    assert verdict.peak_product_c < PARAMS.safe_max_c


def test_untrusted_source_asks_owner() -> None:
    """Una orden desde un documento, aunque sea físicamente segura, escala."""
    action = ProposedAction(kind="defrost", duration_min=20, source="document")
    verdict = verify_action(PARAMS, RoomState(), action)
    assert verdict.decision == "ask_owner"


def test_freezing_setpoint_is_blocked() -> None:
    """Setpoint que congela el producto fresco: block por mínimo seguro."""
    verdict = verify_action(PARAMS, RoomState(), ProposedAction(kind="set_setpoint", value=-5.0))
    assert verdict.decision == "block"
    assert verdict.with_action.product_c[-1] < PARAMS.safe_min_c


def test_minutes_above_so_far_counts_toward_block() -> None:
    """El tiempo ya acumulado sobre el límite se suma al simulado."""
    state = RoomState(minutes_above_so_far=PARAMS.max_minutes_above)
    action = ProposedAction(kind="compressor_off", duration_min=120)
    verdict = verify_action(PARAMS, state, action)
    assert verdict.decision == "block"
    assert verdict.minutes_above_limit >= PARAMS.max_minutes_above


def test_baseline_and_with_action_trajectories_differ() -> None:
    """La línea base no incluye la acción; el escenario con acción sí."""
    verdict = verify_action(
        PARAMS, RoomState(), ProposedAction(kind="compressor_off", duration_min=120)
    )
    assert max(verdict.with_action.product_c) > max(verdict.baseline.product_c)
    assert verdict.evidence["baseline_peak_product_c"] < verdict.evidence["peak_product_c"]


def test_rt04_deferred_compressor_off_not_allowed() -> None:
    """RT-04: apagado que empieza en t=300 (fuera de 240) no pasa allow."""
    action = ProposedAction(
        kind="compressor_off", duration_min=240, start_in_min=300, source="schedule"
    )
    verdict = verify_action(PARAMS, RoomState(), action)
    assert verdict.decision == "block"
    assert verdict.evidence["effective_horizon_min"] >= 300 + 240


def test_rt06_deferred_door_open_not_allowed() -> None:
    """RT-06: puerta que abre en t=260 por 180 min no pasa allow."""
    action = ProposedAction(kind="door_open", duration_min=180, start_in_min=260, source="schedule")
    verdict = verify_action(PARAMS, RoomState(), action)
    assert verdict.decision in ("block", "ask_owner")
    assert verdict.decision != "allow"


def test_rt22_benign_history_plus_deferred_bomb_not_allowed() -> None:
    """RT-22: historial benigno + apagado en t=500 no pasa allow."""
    history = [ProposedAction(kind="door_open", duration_min=5, start_in_min=0)]
    action = ProposedAction(
        kind="compressor_off", duration_min=300, start_in_min=500, source="schedule"
    )
    verdict = verify_action(PARAMS, RoomState(), action, history=history)
    assert verdict.decision in ("block", "ask_owner")
    assert verdict.decision != "allow"


def test_deferred_beyond_simulable_horizon_never_allows() -> None:
    """Si ni extendiendo se puede simular, el techo es ask_owner."""
    action = ProposedAction(
        kind="compressor_off", duration_min=60, start_in_min=100_000, source="schedule"
    )
    verdict = verify_action(PARAMS, RoomState(), action)
    assert verdict.decision == "ask_owner"
    assert verdict.evidence["horizon_capped"] is True


def test_rt15_repeated_defrosts_block_when_approved_go_to_history() -> None:
    """RT-15: lo que el dueño aprueba entra a history y el 3.er deshielo bloquea."""
    history: list[ProposedAction] = []
    decisions = []
    for start in (0, 50, 100):
        action = ProposedAction(
            kind="defrost", duration_min=20, start_in_min=start, source="schedule"
        )
        verdict = verify_action(PARAMS, RoomState(), action, history=list(history))
        decisions.append(verdict.decision)
        history.append(action)  # aprobado/ejecutado: pasa a la history
    assert decisions[0] == "allow"
    assert decisions[-1] == "block"


def test_repeated_forced_defrost_4x30min_in_2h_is_blocked() -> None:
    """Ataque 2-nov: 4 deshielos de 30 min en 2 h; cada uno solo parecería normal."""
    single = verify_action(PARAMS, RoomState(), ProposedAction(kind="defrost", duration_min=30))
    assert single.decision == "allow"
    history = [
        ProposedAction(kind="defrost", duration_min=30, start_in_min=start)
        for start in (0, 30, 60)
    ]
    fourth = ProposedAction(kind="defrost", duration_min=30, start_in_min=90)
    verdict = verify_action(PARAMS, RoomState(), fourth, history=history)
    assert verdict.decision == "block"
    assert verdict.peak_product_c > PARAMS.safe_max_c


def test_verify_action_is_fast_enough() -> None:
    """240 min con dt 30 s debe verificar en menos de 50 ms (mediana)."""
    runs = []
    for _ in range(5):
        start = time.perf_counter()
        verify_action(PARAMS, RoomState(), ProposedAction(kind="defrost", duration_min=20))
        runs.append(time.perf_counter() - start)
    assert sorted(runs)[len(runs) // 2] < 0.05
