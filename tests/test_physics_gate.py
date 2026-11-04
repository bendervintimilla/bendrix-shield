"""Tests deterministas del escudo predictivo físico (sin red)."""

from __future__ import annotations

import time

from shield.physics.contract import ColdRoomParams, ProposedAction, RoomState
from shield.physics.gate import verify_action
from shield.physics.safe_state import last_safe_action

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


def test_salami_soft_drift_to_4_is_not_silent() -> None:
    """Regresión M2 A04/A05: deriva suave a 4.0 °C en pasos chicos no es allow."""
    cases = [
        (3.6, 3.8, [3.2, 3.4, 3.6, 3.8]),
        (3.8, 3.9, [3.3, 3.6, 3.9]),
    ]
    for product_c, setpoint_c, values in cases:
        state = RoomState(air_c=product_c, product_c=product_c, setpoint_c=setpoint_c)
        history = [ProposedAction(kind="set_setpoint", value=value) for value in values]
        verdict = verify_action(
            PARAMS, state, ProposedAction(kind="set_setpoint", value=4.0), history=history
        )
        assert verdict.decision in ("ask_owner", "block")
        assert verdict.decision != "allow"
    # El mismo 4.0 °C en un solo paso legítimo sigue en allow.
    single = verify_action(PARAMS, RoomState(), ProposedAction(kind="set_setpoint", value=4.0))
    assert single.decision == "allow"


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


def test_r2_01_slow_freeze_huge_mass_is_blocked() -> None:
    """R2-01: setpoint -6 °C con 2000 kg; el destino frío manda, no el horizonte."""
    state = RoomState(product_kg=2000.0)
    verdict = verify_action(PARAMS, state, ProposedAction(kind="set_setpoint", value=-6.0))
    assert verdict.decision == "block"
    assert verdict.evidence["cold_destination_block"] is True
    assert verdict.evidence["steady_state_product_c"] == -6.0
    # Dentro del horizonte el producto aún no cruza: el block es analítico.
    assert min(verdict.with_action.product_c) > PARAMS.safe_min_c


def test_r2_02_slow_freeze_moderate_is_blocked() -> None:
    """R2-02: setpoint -3 °C con 1000 kg tampoco pasa allow."""
    state = RoomState(product_kg=1000.0)
    verdict = verify_action(PARAMS, state, ProposedAction(kind="set_setpoint", value=-3.0))
    assert verdict.decision in ("block", "ask_owner")
    assert verdict.decision == "block"


def test_cold_destination_close_to_minimum_asks_owner() -> None:
    """Destino frío a ≤0.5 °C sobre safe_min_c: ask_owner simétrico."""
    state = RoomState(product_kg=2000.0)
    verdict = verify_action(PARAMS, state, ProposedAction(kind="set_setpoint", value=-0.7))
    assert verdict.decision == "ask_owner"


def test_r2_09_autopilot_rescue_cancels_active_defrost() -> None:
    """R2-09: last_safe_action con deshielo activo en history es allow."""
    history = [
        ProposedAction(kind="defrost", duration_min=120, start_in_min=0, source="attacker")
    ]
    action = ProposedAction(
        kind="set_setpoint",
        value=3.0,
        start_in_min=0,
        source="schedule",
        requested_by="wairrior-autopilot",
        note="last_safe_action de M1/M10",
    )
    state = RoomState(air_c=9.0, product_c=4.4, setpoint_c=3.0)
    verdict = verify_action(PARAMS, state, action, history=history)
    assert verdict.decision == "allow"
    assert verdict.evidence["rescue_action"] is True
    assert verdict.evidence["improves_over_doing_nothing"] is True
    assert verdict.peak_product_c < PARAMS.safe_max_c


def test_r2_10_autopilot_rescue_cancels_active_compressor_off() -> None:
    """R2-10: last_safe_action con compressor_off activo en history es allow."""
    history = [
        ProposedAction(kind="compressor_off", duration_min=180, start_in_min=0, source="attacker")
    ]
    action = ProposedAction(
        kind="set_setpoint",
        value=3.0,
        start_in_min=0,
        source="schedule",
        requested_by="wairrior-autopilot",
        note="last_safe_action de M1/M10",
    )
    state = RoomState(air_c=8.0, product_c=4.3, setpoint_c=3.0)
    verdict = verify_action(PARAMS, state, action, history=history)
    assert verdict.decision == "allow"
    assert verdict.evidence["rescue_action"] is True
    assert verdict.peak_product_c < PARAMS.safe_max_c


def test_rescue_during_active_defrost_with_tight_margin_allows_immediately() -> None:
    """Rescate con producto a 4.5 °C y deshielo activo: allow, no ask por margen."""
    state = RoomState(air_c=9.0, product_c=4.5)
    history = [ProposedAction(kind="defrost", duration_min=240, source="attacker")]
    verdict = verify_action(PARAMS, state, last_safe_action(PARAMS, state), history=history)
    assert verdict.decision == "allow"
    assert verdict.evidence["summary"].startswith(
        "contención reversible: mejora frente a no hacer nada; margen restante"
    )
    assert verdict.evidence["remaining_margin_c"] < 0.5
    assert verdict.evidence["peak_without_action_c"] > verdict.evidence["peak_product_c"]


def test_verify_action_is_fast_enough() -> None:
    """240 min con dt 30 s debe verificar en menos de 50 ms (mediana)."""
    runs = []
    for _ in range(5):
        start = time.perf_counter()
        verify_action(PARAMS, RoomState(), ProposedAction(kind="defrost", duration_min=20))
        runs.append(time.perf_counter() - start)
    assert sorted(runs)[len(runs) // 2] < 0.05
