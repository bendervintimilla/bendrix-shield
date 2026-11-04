"""Tests deterministas del gemelo térmico (sin red, solo stdlib)."""

from __future__ import annotations

import pytest

from shield.physics.contract import ColdRoomParams, ProposedAction, RoomState
from shield.physics.gate import verify_action
from shield.physics.presets import CHILLER_PARAMS, FREEZER_PARAMS
from shield.physics.safe_state import factory_setpoint_c, last_safe_action
from shield.physics.thermal import simulate

PARAMS = ColdRoomParams()


def test_stable_closed_room_stays_within_hysteresis() -> None:
    """Sin acciones, aire en setpoint ±histéresis y producto casi quieto."""
    traj = simulate(PARAMS, RoomState(), [], horizon_min=240)
    assert len(traj.t_min) == 240 * 2 + 1
    for air in traj.air_c:
        assert 3.0 - PARAMS.hysteresis_c <= air <= 3.0 + PARAMS.hysteresis_c
    assert max(traj.product_c) - min(traj.product_c) < 0.5
    assert abs(traj.product_c[-1] - 3.0) < 0.5


def test_door_open_20min_raises_air_but_barely_product() -> None:
    """Puerta abierta 20 min: el aire sube fuerte, el producto apenas."""
    action = ProposedAction(kind="door_open", duration_min=20)
    traj = simulate(PARAMS, RoomState(), [action], horizon_min=60)
    assert max(traj.air_c) > 8.0
    assert max(traj.product_c) < 4.0
    assert max(traj.product_c) - 3.0 < 1.0


def test_compressor_off_6h_breaks_safe_max() -> None:
    """Apagado de 6 h: el producto supera el máximo seguro."""
    action = ProposedAction(kind="compressor_off", duration_min=360)
    traj = simulate(PARAMS, RoomState(), [action], horizon_min=360)
    assert max(traj.product_c) > PARAMS.safe_max_c
    assert traj.product_c[-1] > PARAMS.safe_max_c


def test_deterministic_and_does_not_mutate_state() -> None:
    """Misma entrada, misma salida; el estado del llamador no cambia."""
    state = RoomState()
    actions = [ProposedAction(kind="defrost", duration_min=20)]
    first = simulate(PARAMS, state, actions, horizon_min=120)
    second = simulate(PARAMS, state, actions, horizon_min=120)
    assert first.t_min == second.t_min
    assert first.air_c == second.air_c
    assert first.product_c == second.product_c
    assert state.air_c == 3.0 and state.product_c == 3.0 and not state.compressor_on


def test_load_product_mixes_at_ambient_temperature() -> None:
    """30 kg a ambient_c sobre 200 kg a 3 °C mezclan según balance de masa."""
    action = ProposedAction(kind="load_product", value=30.0)
    traj = simulate(PARAMS, RoomState(), [action], horizon_min=30)
    expected_mix = (200.0 * 3.0 + 30.0 * PARAMS.ambient_c) / 230.0
    # Tras el primer paso el producto ya mezcló y empieza a enfriarse.
    assert traj.product_c[1] == pytest.approx(expected_mix, abs=0.15)
    assert max(traj.product_c) <= expected_mix + 0.01


def test_defrost_warms_air_and_turns_compressor_off() -> None:
    """Deshielo: calefactor on y compresor off durante el ciclo."""
    action = ProposedAction(kind="defrost", duration_min=20)
    traj = simulate(PARAMS, RoomState(), [action], horizon_min=60)
    assert max(traj.air_c) > 6.0
    assert not any(traj.compressor_on[1:41])  # primeros 20 min de pasos


def test_setpoint_change_is_permanent_and_delayed_start_works() -> None:
    """El setpoint nuevo rige desde start_in_min hasta el horizonte."""
    action = ProposedAction(kind="set_setpoint", value=2.0, start_in_min=60)
    traj = simulate(PARAMS, RoomState(), [action], horizon_min=240)
    assert traj.product_c[-1] < 2.6
    assert traj.product_c[-1] < traj.product_c[0]


def test_freezer_preset_holds_minus18_and_forced_defrost_breaks() -> None:
    """Congelador: estable a -18 °C; un deshielo forzado largo rompe -15 °C."""
    state = RoomState(air_c=-18.0, product_c=-18.0, setpoint_c=-18.0)
    traj = simulate(FREEZER_PARAMS, state, [], horizon_min=240)
    assert max(traj.product_c) < FREEZER_PARAMS.safe_max_c
    assert abs(traj.product_c[-1] - (-18.0)) < 1.5
    verdict = verify_action(
        FREEZER_PARAMS, state, ProposedAction(kind="defrost", duration_min=240)
    )
    assert verdict.decision == "block"
    assert verdict.peak_product_c > FREEZER_PARAMS.safe_max_c


def test_chiller_preset_holds_2c() -> None:
    """Chiller: estable cerca de su setpoint de fábrica de 2 °C."""
    state = RoomState(air_c=2.0, product_c=2.0, setpoint_c=2.0)
    traj = simulate(CHILLER_PARAMS, state, [], horizon_min=240)
    assert abs(traj.product_c[-1] - 2.0) < 1.0
    assert max(traj.product_c) < CHILLER_PARAMS.safe_max_c


def test_last_safe_action_restores_factory_setpoint() -> None:
    """Estado seguro: setpoint de fábrica, reversible y verificable en allow."""
    drifted = RoomState(air_c=-18.0, product_c=-18.0, setpoint_c=-10.0)
    action = last_safe_action(FREEZER_PARAMS, drifted)
    assert action.kind == "set_setpoint"
    assert action.value == -18.0
    assert action.equipment == "congelador"
    assert "reversible" in action.note
    assert verify_action(FREEZER_PARAMS, drifted, action).decision == "allow"
    assert factory_setpoint_c(PARAMS) == 3.0
    assert factory_setpoint_c(CHILLER_PARAMS) == 2.0
    assert last_safe_action(PARAMS, RoomState(setpoint_c=4.5)).value == 3.0


def test_invalid_inputs_raise() -> None:
    """Entradas inválidas fallan con ValueError, no con resultados raros."""
    with pytest.raises(ValueError):
        simulate(PARAMS, RoomState(), [], dt_s=0)
    with pytest.raises(ValueError):
        simulate(PARAMS, RoomState(), [ProposedAction(kind="set_setpoint")])
    with pytest.raises(ValueError):
        simulate(PARAMS, RoomState(), [ProposedAction(kind="load_product", value=-1)])
