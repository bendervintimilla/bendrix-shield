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


def test_single_setpoint_near_limit_asks_owner_not_blocks() -> None:
    """Un solo salto a 4 °C reduce el margen: ask_owner, no block."""
    verdict = verify_action(PARAMS, RoomState(), ProposedAction(kind="set_setpoint", value=4.0))
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


def test_verify_action_is_fast_enough() -> None:
    """240 min con dt 30 s debe verificar en menos de 50 ms (mediana)."""
    runs = []
    for _ in range(5):
        start = time.perf_counter()
        verify_action(PARAMS, RoomState(), ProposedAction(kind="defrost", duration_min=20))
        runs.append(time.perf_counter() - start)
    assert sorted(runs)[len(runs) // 2] < 0.05
