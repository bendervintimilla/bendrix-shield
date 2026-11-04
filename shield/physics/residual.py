"""Detector de sensor falsificado por residuo físico (M6).

Idea: el sensor puede mentir, pero la física no. Dados los actuadores
registrados (compresor, puerta, setpoint) en ``state_history``, se predice
la temperatura del aire con el gemelo térmico de M1
(``shield.physics.thermal.simulate``) y se compara con ``reported``, lo
que el sensor dice haber medido. Si el residuo (reportado - predicho) es
físicamente imposible de forma sostenida, la lectura es falsa: spoofing
o sensor congelado.

Umbral y ventana (supuestos rotulados, no mediciones de equipo real):
- ``THRESHOLD_C = 2.0`` °C de residuo medio absoluto sostenido. Un sensor
  sano con ruido gaussiano típico (sigma 0.3 °C) queda muy por debajo;
  la tasa de falsos positivos medida está en
  ``tests/test_physics_residual.py`` (series legítimas con ruido
  gaussiano, semilla fija).
- ``WINDOW_MIN = 20.0`` minutos: el residuo debe sostenerse una ventana
  completa; un pico breve no marca spoofing.
- Sensor congelado: desviación estándar de lo reportado < 0.05 °C en la
  ventana mientras lo predicho se mueve más de 1.0 °C.

Si M1 aún no está fusionado, se usa un integrador interno de dos nodos
(aire + producto, Euler explícito) con los actuadores registrados paso a
paso; en cuanto ``thermal.simulate`` existe, pasa a ser la fuente de la
predicción. Todo determinista, sin red, solo stdlib.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

from shield.physics.contract import ColdRoomParams, ProposedAction, RoomState

THRESHOLD_C = 2.0
WINDOW_MIN = 20.0
STUCK_STD_C = 0.05
STUCK_PREDICTED_RANGE_C = 1.0
_DT_S = 30.0


def _get(state: Any, name: str, default: Any) -> Any:
    """Lee un campo de un RoomState o de un dict equivalente."""
    if isinstance(state, dict):
        return state.get(name, default)
    return getattr(state, name, default)


def _as_state(state: Any) -> RoomState:
    """Normaliza un elemento del historial a RoomState."""
    if isinstance(state, RoomState):
        return state
    return RoomState(
        t_min=float(_get(state, "t_min", 0.0)),
        air_c=float(_get(state, "air_c", 3.0)),
        product_c=float(_get(state, "product_c", 3.0)),
        product_kg=float(_get(state, "product_kg", 200.0)),
        setpoint_c=float(_get(state, "setpoint_c", 3.0)),
        compressor_on=bool(_get(state, "compressor_on", False)),
        door_open=bool(_get(state, "door_open", False)),
        minutes_above_so_far=float(_get(state, "minutes_above_so_far", 0.0)),
    )


def _cadence_min(states: list[RoomState]) -> float:
    """Cadencia entre muestras en minutos (1.0 si no se puede inferir)."""
    if len(states) < 2:
        return 1.0
    diffs = [
        b.t_min - a.t_min for a, b in zip(states, states[1:], strict=False) if b.t_min > a.t_min
    ]
    if not diffs:
        return 1.0
    return sum(diffs) / len(diffs)


def _actions_from_history(states: list[RoomState], dt_min: float) -> list[ProposedAction]:
    """Reconstruye acciones para simulate() desde los actuadores registrados.

    Cada tramo con puerta abierta es un ``door_open``; cada tramo con el
    compresor apagado es un ``compressor_off`` (si el termostato también
    lo hubiera apagado, el efecto es el mismo; si no, captura el apagado
    real); cada cambio de setpoint es un ``set_setpoint``.
    """
    actions: list[ProposedAction] = []
    t0 = states[0].t_min

    def _segments(key: str) -> list[tuple[float, float]]:
        segs: list[tuple[float, float]] = []
        start: int | None = None
        for i, s in enumerate(states):
            if bool(_get(s, key, False)) and start is None:
                start = i
            elif not bool(_get(s, key, False)) and start is not None:
                segs.append((states[start].t_min - t0, (i - start) * dt_min))
                start = None
        if start is not None:
            segs.append((states[start].t_min - t0, (len(states) - start) * dt_min))
        return segs

    for start, dur in _segments("door_open"):
        actions.append(ProposedAction(kind="door_open", start_in_min=start, duration_min=dur))
    # Tramos con compresor apagado = complemento de los tramos encendidos.
    on_segs = _segments("compressor_on")
    cursor = 0.0
    horizon = (len(states) - 1) * dt_min
    for start, dur in on_segs:
        if start > cursor:
            actions.append(
                ProposedAction(
                    kind="compressor_off", start_in_min=cursor, duration_min=start - cursor
                )
            )
        cursor = max(cursor, start + dur)
    if cursor < horizon:
        actions.append(
            ProposedAction(
                kind="compressor_off", start_in_min=cursor, duration_min=horizon - cursor
            )
        )
    elif not on_segs:
        actions.append(
            ProposedAction(
                kind="compressor_off", start_in_min=0.0, duration_min=max(horizon, dt_min)
            )
        )
    prev_sp = states[0].setpoint_c
    for s in states[1:]:
        if s.setpoint_c != prev_sp:
            actions.append(
                ProposedAction(
                    kind="set_setpoint",
                    value=float(s.setpoint_c),
                    start_in_min=s.t_min - t0,
                    duration_min=0.0,
                )
            )
            prev_sp = s.setpoint_c
    return actions


def _predict_with_simulate(
    params: ColdRoomParams, states: list[RoomState], dt_min: float
) -> tuple[list[float], list[float]] | None:
    """Predice (aire, producto) con M1; None si simulate aún no existe."""
    try:
        from shield.physics.thermal import simulate
    except ImportError:
        return None
    initial = replace(states[0])
    horizon = max((len(states) - 1) * dt_min, dt_min)
    traj = simulate(params, initial, _actions_from_history(states, dt_min),
                    horizon_min=horizon, dt_s=_DT_S)
    if not traj.t_min:
        return None
    step_min = (traj.t_min[1] - traj.t_min[0]) if len(traj.t_min) > 1 else _DT_S / 60.0
    if step_min <= 0:
        step_min = _DT_S / 60.0
    air_out: list[float] = []
    prod_out: list[float] = []
    for s in states:
        idx = int(round((s.t_min - states[0].t_min) / step_min))
        idx = min(max(idx, 0), len(traj.air_c) - 1)
        air_out.append(float(traj.air_c[idx]))
        prod_out.append(float(traj.product_c[idx]))
    return air_out, prod_out


def _predict_internal(
    params: ColdRoomParams, states: list[RoomState], dt_min: float
) -> tuple[list[float], list[float]]:
    """Integrador de dos nodos con los actuadores registrados paso a paso."""
    air = float(states[0].air_c)
    product = float(states[0].product_c)
    out = [air]
    prod_out = [product]
    sub = max(1, int(round(dt_min * 60.0 / _DT_S)))
    h = dt_min * 60.0 / sub
    # Los actuadores de la muestra i rigen el intervalo i -> i+1.
    for s in states[:-1]:
        ua = params.ua_wall_w_per_k + (
            params.ua_door_open_w_per_k if s.door_open else 0.0
        )
        # Mismo acople que M1: ha_air_product directo, sin escalar por kg.
        ha = params.ha_air_product_w_per_k if s.product_kg > 0 else 0.0
        c_prod = max(s.product_kg, 0.0) * params.product_cp_j_per_kgk
        cooling = params.cooling_capacity_w if s.compressor_on else 0.0
        for _ in range(sub):
            d_air = (
                ua * (params.ambient_c - air) + ha * (product - air) - cooling
            ) / params.air_mass_j_per_k
            d_prod = ha * (air - product) / c_prod if c_prod > 0 else 0.0
            air += d_air * h
            product += d_prod * h
        out.append(air)
        prod_out.append(product)
    return out, prod_out


def _std(values: list[float]) -> float:
    """Desviación estándar poblacional."""
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def check_sensor(
    params: ColdRoomParams,
    state_history: list[Any],
    reported: list[float],
) -> dict[str, Any]:
    """Compara lo reportado por el sensor con la predicción física.

    Devuelve dict con ``spoofed`` (bool), ``residual_c`` (residuo absoluto
    máximo en °C), ``window_min``/``ventana_min`` (ventana evaluada en
    minutos), ``threshold_c`` y ``explanation`` (una frase), más detalle
    de diagnóstico. Marca spoofing si el residuo medio absoluto supera
    ``THRESHOLD_C`` durante ``WINDOW_MIN`` o si el sensor está congelado
    mientras la predicción se mueve.
    """
    states = [_as_state(s) for s in state_history]
    reps = [float(r) for r in reported]
    n = min(len(states), len(reps))
    if n == 0:
        return {
            "spoofed": False,
            "residual_c": 0.0,
            "window_min": 0.0,
            "ventana_min": 0.0,
            "threshold_c": THRESHOLD_C,
            "explanation": "Sin datos suficientes para evaluar el sensor.",
            "explicacion": "Sin datos suficientes para evaluar el sensor.",
            "mean_abs_residual_c": 0.0,
            "stuck": False,
            "n_samples": 0,
            "predicted_product_last_c": 0.0,
            "predicted_minutes_above": 0.0,
            "simulated": True,
        }
    states, reps = states[:n], reps[:n]
    dt_min = _cadence_min(states)
    both = _predict_with_simulate(params, states, dt_min)
    source = "thermal.simulate"
    if both is None:
        both = _predict_internal(params, states, dt_min)
        source = "integrador interno (M1 aún no fusionado)"
    predicted, predicted_product = both
    predicted_minutes_above = sum(
        dt_min for p in predicted_product if p > params.safe_max_c
    )

    residuals = [r - p for r, p in zip(reps, predicted, strict=True)]
    abs_res = [abs(r) for r in residuals]
    residual_c = max(abs_res) if abs_res else 0.0
    mean_abs = sum(abs_res) / len(abs_res) if abs_res else 0.0
    duration_min = (n - 1) * dt_min if n > 1 else dt_min

    win = max(1, int(round(WINDOW_MIN / dt_min))) if dt_min > 0 else n
    sustained = False
    worst_window_mean = mean_abs
    # Ventanas completas de WINDOW_MIN; si la serie es más corta, vale entera.
    starts = range(0, n - win + 1) if n > win else range(0, 1)
    for i in starts:
        chunk = abs_res[i : i + win] if n > win else abs_res
        m = sum(chunk) / len(chunk)
        worst_window_mean = max(worst_window_mean, m)
        if m > THRESHOLD_C:
            sustained = True
    stuck = (
        duration_min >= WINDOW_MIN
        and _std(reps) < STUCK_STD_C
        and (max(predicted) - min(predicted)) > STUCK_PREDICTED_RANGE_C
    )
    spoofed = bool(sustained or stuck)

    if stuck and not sustained:
        explanation = (
            "Sensor congelado: reporta un valor plano mientras la física "
            "predice un cambio mayor a 1 °C."
        )
    elif sustained:
        explanation = (
            f"Residuo físico imposible: lo reportado se aparta de la "
            f"predicción más de {THRESHOLD_C} °C durante {WINDOW_MIN:.0f} min."
        )
    else:
        explanation = "El sensor es consistente con la física predicha."

    return {
        "spoofed": spoofed,
        "residual_c": round(float(residual_c), 3),
        "window_min": round(float(duration_min), 2),
        "ventana_min": round(float(duration_min), 2),
        "threshold_c": THRESHOLD_C,
        "explanation": explanation,
        "explicacion": explanation,
        "mean_abs_residual_c": round(float(mean_abs), 3),
        "worst_window_mean_abs_residual_c": round(float(worst_window_mean), 3),
        "stuck": bool(stuck),
        "sustained_residual": bool(sustained),
        "n_samples": n,
        "dt_min": dt_min,
        "prediction_source": source,
        "predicted_last_c": round(float(predicted[-1]), 3),
        "predicted_product_last_c": round(float(predicted_product[-1]), 3),
        "predicted_minutes_above": round(float(predicted_minutes_above), 2),
        "reported_last_c": round(float(reps[-1]), 3),
        "simulated": True,
    }
