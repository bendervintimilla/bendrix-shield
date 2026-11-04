"""Escudo predictivo: verifica una acción física antes de ejecutarla.

Simula la línea base (estado actual, sin la acción) y el escenario con
``history + action``, y decide según la trayectoria del PRODUCTO:

- ``block``: el producto pasa más de ``max_minutes_above`` minutos sobre
  ``safe_max_c`` (sumando ``state.minutes_above_so_far``), baja de
  ``safe_min_c``, o la deriva acumulada de setpoints (salami: varios
  pasos chicos ya aceptados en ``history`` más la acción nueva) deja el
  pico a menos de 1 °C del límite. Cada paso puede estar «en rango» y
  aun así la suma rompe el margen: por eso se simula la historia junta.
- ``ask_owner``: no rompe la envolvente, pero el pico queda a menos de
  1 °C de ``safe_max_c``, hay una ruptura breve dentro de la tolerancia,
  o la fuente no es confiable (documento, atacante o fuente desconocida).
- ``allow``: el resto.

Todo lo reportado es ``simulated``: sale del gemelo de
:mod:`shield.physics.thermal`, no de un equipo real.
"""

from __future__ import annotations

from shield.physics.contract import (
    ColdRoomParams,
    PhysicalVerdict,
    ProposedAction,
    RoomState,
    Trajectory,
)
from shield.physics.thermal import simulate

TRUSTED_SOURCES = frozenset({"agent", "schedule", "voice"})
_DT_S = 30.0
# Deriva lenta: a partir de estos acumulados se escala ask_owner a block.
_DRIFT_MIN_STEPS = 3
_DRIFT_MIN_CUMULATIVE_C = 2.0


def _metrics(
    params: ColdRoomParams, trajectory: Trajectory, dt_s: float = _DT_S
) -> tuple[float, float, float | None, float]:
    """(pico, mínimo, primera ruptura en min desde t0, minutos sobre el máximo)."""
    peak = max(trajectory.product_c)
    minimum = min(trajectory.product_c)
    breach_min: float | None = None
    minutes_above = 0.0
    t0 = trajectory.t_min[0]
    for t_min, product_c in zip(trajectory.t_min, trajectory.product_c, strict=True):
        if product_c > params.safe_max_c:
            if breach_min is None:
                breach_min = t_min - t0
            minutes_above += dt_s / 60.0
    # El punto inicial no representa un paso completo; si ya nace sobre el
    # límite, la ruptura es en 0 y su duración la cubre el paso siguiente.
    if trajectory.product_c[0] > params.safe_max_c:
        breach_min = 0.0
        minutes_above = max(minutes_above - dt_s / 60.0, 0.0)
    return peak, minimum, breach_min, minutes_above


def _setpoint_drift(
    state: RoomState, actions: list[ProposedAction]
) -> tuple[float, float, int]:
    """(deriva acumulada hacia arriba °C, setpoint final °C, nº de pasos)."""
    ordered = sorted(enumerate(actions), key=lambda item: (item[1].start_in_min, item[0]))
    previous = float(state.setpoint_c)
    final = previous
    cumulative_up = 0.0
    steps = 0
    for _, action in ordered:
        if action.kind != "set_setpoint" or action.value is None:
            continue
        steps += 1
        if action.value > previous:
            cumulative_up += action.value - previous
        previous = float(action.value)
        final = previous
    return cumulative_up, final, steps


def verify_action(
    params: ColdRoomParams,
    state: RoomState,
    action: ProposedAction,
    history: list[ProposedAction] | None = None,
    horizon_min: float = 240,
) -> PhysicalVerdict:
    """Decide allow / ask_owner / block simulando antes de actuar."""
    past = list(history or [])
    baseline = simulate(params, state, [], horizon_min=horizon_min, dt_s=_DT_S)
    with_action = simulate(params, state, [*past, action], horizon_min=horizon_min, dt_s=_DT_S)

    peak, minimum, breach_min, minutes_above_sim = _metrics(params, with_action)
    baseline_peak, _, _, _ = _metrics(params, baseline)
    minutes_above_total = float(state.minutes_above_so_far) + minutes_above_sim
    drift_up, final_setpoint, setpoint_steps = _setpoint_drift(state, [*past, action])
    margin_c = params.safe_max_c - peak
    # Un setpoint es permanente: aunque el producto tarde en llegar, su
    # destino es ese setpoint. El margen de decisión usa ese destino.
    decision_peak = max(peak, final_setpoint) if setpoint_steps else peak
    decision_margin_c = params.safe_max_c - decision_peak

    drift_block = (
        setpoint_steps >= _DRIFT_MIN_STEPS
        and drift_up >= _DRIFT_MIN_CUMULATIVE_C
        and decision_margin_c <= 1.0
    )

    if minimum < params.safe_min_c:
        decision = "block"
        detail = (
            f"el producto baja a {minimum:.1f} °C, bajo el mínimo seguro "
            f"de {params.safe_min_c:.1f} °C"
        )
    elif minutes_above_total > params.max_minutes_above:
        decision = "block"
        when = f" en {breach_min:.0f} min" if breach_min is not None else ""
        detail = (
            f"el producto supera {params.safe_max_c:.1f} °C{when} y llega a "
            f"{peak:.1f} °C; {minutes_above_total:.0f} min sobre el límite"
        )
    elif drift_block:
        decision = "block"
        detail = (
            f"deriva lenta de setpoint: {setpoint_steps} pasos suman "
            f"+{drift_up:.1f} °C hasta {final_setpoint:.1f} °C y el producto "
            f"llega a {peak:.1f} °C, a {decision_margin_c:.1f} °C del límite"
        )
    elif breach_min is not None or decision_margin_c <= 1.0:
        decision = "ask_owner"
        detail = (
            f"el producto llega a {peak:.1f} °C, a {decision_margin_c:.1f} °C del "
            f"límite de {params.safe_max_c:.1f} °C"
        )
    elif action.source not in TRUSTED_SOURCES:
        decision = "ask_owner"
        detail = (
            f"fuente no confiable ({action.source}); el producto llega "
            f"a {peak:.1f} °C, bajo el límite de {params.safe_max_c:.1f} °C"
        )
    else:
        decision = "allow"
        detail = (
            f"el producto se mantiene en máximo {peak:.1f} °C, bajo el "
            f"límite de {params.safe_max_c:.1f} °C"
        )

    evidence = {
        "simulated": True,
        "summary": detail,
        "peak_product_c": round(peak, 3),
        "baseline_peak_product_c": round(baseline_peak, 3),
        "min_product_c": round(minimum, 3),
        "margin_to_safe_max_c": round(margin_c, 3),
        "minutes_above_limit": round(minutes_above_total, 2),
        "minutes_above_so_far": float(state.minutes_above_so_far),
        "predicted_breach_min": breach_min,
        "effective_setpoint_c": final_setpoint,
        "cumulative_setpoint_drift_c": round(drift_up, 3),
        "setpoint_steps": setpoint_steps,
        "history_actions": len(past),
        "source": action.source,
        "requested_by": action.requested_by,
        "horizon_min": horizon_min,
        "dt_s": _DT_S,
    }
    return PhysicalVerdict(
        decision=decision,
        reason=detail,
        predicted_breach_min=breach_min,
        peak_product_c=peak,
        minutes_above_limit=minutes_above_total,
        baseline=baseline,
        with_action=with_action,
        evidence=evidence,
    )
