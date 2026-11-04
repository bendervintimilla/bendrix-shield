"""Escudo predictivo: verifica una acción física antes de ejecutarla.

Simula la línea base (estado actual, sin la acción) y el escenario con
``history + action``, y decide según la trayectoria del PRODUCTO:

- ``block``: el producto pasa más de ``max_minutes_above`` minutos sobre
  ``safe_max_c`` (sumando ``state.minutes_above_so_far``), baja de
  ``safe_min_c``, o la deriva acumulada de setpoints (salami: varios
  pasos chicos ya aceptados en ``history`` más la acción nueva) deja el
  pico a menos de 1 °C del límite. Cada paso puede estar «en rango» y
  aun así la suma rompe el margen: por eso se simula la historia junta.
- ``ask_owner``: no rompe la envolvente, pero el pico (o el setpoint
  permanente destino) queda a 0.5 °C o menos de ``safe_max_c``, hay una
  ruptura breve dentro de la tolerancia, la fuente no es confiable
  (documento, atacante o fuente desconocida), o la acción empieza tan
  lejos que no se puede simular entera. Nunca se permite sin simular:
  el horizonte efectivo cubre inicio + duración + recuperación de la
  acción y de cada acción de ``history`` (hallazgo RT-04/06/22 de M7).
- ``allow``: el resto. Un setpoint en 4.0 °C con pico simulado lejos
  del límite es legítimo: se permite informando el margen en la
  evidencia, sin fricción de aprobación.

Simetría fría (R2-01/R2-02): el destino de un setpoint permanente es
su estado estacionario analítico; bajo ``safe_min_c`` es ``block`` y
a 0.5 °C o menos sobre el mínimo es ``ask_owner``, igual que el lado
caliente. La contención del autopiloto (``last_safe_action``) cancela
en el gemelo el deshielo/apagado activo y, si mejora la trayectoria
frente a no hacer nada, es ``allow`` inmediato: el ``ask_owner`` por
margen nunca aplica a un rescate (R2-09/R2-10).

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
from shield.physics.safe_state import factory_setpoint_c
from shield.physics.thermal import simulate

TRUSTED_SOURCES = frozenset({"agent", "schedule", "voice"})
_DT_S = 30.0
# Deriva lenta: a partir de estos acumulados se escala ask_owner a block.
_DRIFT_MIN_STEPS = 3
_DRIFT_MIN_CUMULATIVE_C = 2.0
# Margen (pico o setpoint destino) que escala a ask_owner.
_ASK_MARGIN_C = 0.5
# Cola simulada tras el fin de cada acción y tope del horizonte efectivo.
_RECOVERY_MIN = 240.0
_MAX_EFFECTIVE_HORIZON_MIN = 1_440.0


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


def _effective_horizon(actions: list[ProposedAction], horizon_min: float) -> tuple[float, bool]:
    """(horizonte a simular, True si ni extendiendo se cubre todo).

    Cubre, para cada acción, inicio + duración + recuperación. Las
    acciones permanentes o instantáneas duran 0 a este efecto, pero
    igual reciben su cola de recuperación desde que empiezan.
    """
    required = float(horizon_min)
    for action in actions:
        start = max(float(action.start_in_min), 0.0)
        duration = (
            max(float(action.duration_min), 0.0)
            if action.kind in ("compressor_off", "defrost", "door_open")
            else 0.0
        )
        required = max(required, start + duration + _RECOVERY_MIN)
    cap = max(_MAX_EFFECTIVE_HORIZON_MIN, float(horizon_min))
    return min(required, cap), required > cap


def _is_rescue(params: ColdRoomParams, action: ProposedAction) -> bool:
    """True si es la contención del autopiloto al setpoint de fábrica."""
    return (
        action.kind == "set_setpoint"
        and action.requested_by == "wairrior-autopilot"
        and action.value is not None
        and abs(action.value - factory_setpoint_c(params)) < 1e-9
    )


def verify_action(
    params: ColdRoomParams,
    state: RoomState,
    action: ProposedAction,
    history: list[ProposedAction] | None = None,
    horizon_min: float = 240,
) -> PhysicalVerdict:
    """Decide allow / ask_owner / block simulando antes de actuar."""
    past = list(history or [])
    effective_horizon, horizon_capped = _effective_horizon([*past, action], horizon_min)
    baseline = simulate(params, state, [], horizon_min=effective_horizon, dt_s=_DT_S)
    with_action = simulate(
        params, state, [*past, action], horizon_min=effective_horizon, dt_s=_DT_S
    )

    peak, minimum, breach_min, minutes_above_sim = _metrics(params, with_action)
    baseline_peak, _, _, _ = _metrics(params, baseline)
    minutes_above_total = float(state.minutes_above_so_far) + minutes_above_sim
    drift_up, final_setpoint, setpoint_steps = _setpoint_drift(state, [*past, action])
    margin_c = params.safe_max_c - peak
    # Un setpoint es permanente: su destino cuenta solo si queda a
    # _ASK_MARGIN_C del límite; un destino a 4.0 °C (margen 1.0 °C)
    # es legítimo y no debe generar fricción de aprobación.
    destination_margin_c = params.safe_max_c - final_setpoint if setpoint_steps else margin_c
    decision_margin_c = min(margin_c, destination_margin_c)
    # Destino frío simétrico (R2-01/R2-02): un setpoint permanente es el
    # estado estacionario analítico del producto. Bajo safe_min_c es
    # block aunque la masa tarde más que el horizonte en llegar; a
    # _ASK_MARGIN_C o menos sobre el mínimo es ask_owner.
    cold_destination_block = bool(setpoint_steps) and final_setpoint < params.safe_min_c
    cold_margin_c = (
        final_setpoint - params.safe_min_c if setpoint_steps else minimum - params.safe_min_c
    )

    drift_block = (
        setpoint_steps >= _DRIFT_MIN_STEPS
        and drift_up >= _DRIFT_MIN_CUMULATIVE_C
        and destination_margin_c <= 1.0
    )
    # Salami suave (regresión M2 A04/A05): pasos chicos repetidos que
    # terminan a ≤1 °C del límite no pasan en silencio, aunque un único
    # setpoint a ese mismo valor sea legítimo y se permita.
    salami_ask = (
        action.kind == "set_setpoint"
        and setpoint_steps >= _DRIFT_MIN_STEPS
        and drift_up >= 0.6
        and destination_margin_c <= 1.0
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
    elif cold_destination_block:
        decision = "block"
        detail = (
            f"destino frío imposible: el setpoint permanente "
            f"{final_setpoint:.1f} °C deja el producto bajo el mínimo "
            f"seguro de {params.safe_min_c:.1f} °C"
        )
    elif drift_block:
        decision = "block"
        detail = (
            f"deriva lenta de setpoint: {setpoint_steps} pasos suman "
            f"+{drift_up:.1f} °C hasta {final_setpoint:.1f} °C y el producto "
            f"llega a {peak:.1f} °C, a {decision_margin_c:.1f} °C del límite"
        )
    elif (
        breach_min is not None
        or decision_margin_c <= _ASK_MARGIN_C
        or cold_margin_c <= _ASK_MARGIN_C
        or salami_ask
    ):
        decision = "ask_owner"
        if salami_ask and breach_min is None and decision_margin_c > _ASK_MARGIN_C:
            detail = (
                f"deriva por pasos chicos: {setpoint_steps} setpoints suman "
                f"+{drift_up:.1f} °C hasta {final_setpoint:.1f} °C, a "
                f"{destination_margin_c:.1f} °C del límite; el producto "
                f"llega a {peak:.1f} °C"
            )
        elif breach_min is None and cold_margin_c <= _ASK_MARGIN_C < decision_margin_c:
            detail = (
                f"el producto baja a {minimum:.1f} °C, a {cold_margin_c:.1f} °C del "
                f"mínimo seguro de {params.safe_min_c:.1f} °C"
            )
        else:
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

    # Contención del autopiloto: el gemelo ya cortó el deshielo/apagado
    # activo al inicio del rescate. Regla dura adicional: una acción de
    # rescate que mejora la trayectoria frente a no hacer nada (la
    # history siguiendo su curso) es allow inmediato.
    rescue = _is_rescue(params, action)
    improves = False
    no_action_peak: float | None = None
    if rescue and past:
        no_action_traj = simulate(
            params, state, list(past), horizon_min=effective_horizon, dt_s=_DT_S
        )
        no_action_peak, no_action_min, _, no_action_minutes = _metrics(params, no_action_traj)
        improves = (
            peak < no_action_peak - 1e-9
            and minutes_above_total <= float(state.minutes_above_so_far) + no_action_minutes + 1e-9
            # Enfriar hacia el setpoint seguro no es empeorar el lado
            # frío: empeorar es cruzar safe_min_c o bajar del no-acción.
            and (minimum >= params.safe_min_c or minimum >= no_action_min - 1e-9)
        )
        if improves:
            # Contain first: el ask_owner por margen nunca aplica a un
            # rescate que mejora; es allow inmediato.
            decision = "allow"
            detail = (
                f"contención reversible: mejora frente a no hacer nada; "
                f"margen restante {margin_c:.1f} °C"
            )

    if horizon_capped and decision == "allow":
        # Nunca allow sin haber simulado la acción completa.
        decision = "ask_owner"
        detail = (
            f"acción diferida fuera del horizonte simulable "
            f"(empieza en {action.start_in_min:.0f} min); no se permite "
            f"sin revisión del dueño"
        )

    evidence = {
        "simulated": True,
        "summary": detail,
        "peak_product_c": round(peak, 3),
        "baseline_peak_product_c": round(baseline_peak, 3),
        "min_product_c": round(minimum, 3),
        "margin_to_safe_max_c": round(margin_c, 3),
        "remaining_margin_c": round(margin_c, 3),
        "minutes_above_limit": round(minutes_above_total, 2),
        "minutes_above_so_far": float(state.minutes_above_so_far),
        "predicted_breach_min": breach_min,
        "effective_setpoint_c": final_setpoint,
        "steady_state_product_c": final_setpoint if setpoint_steps else None,
        "cold_destination_block": cold_destination_block,
        "rescue_action": rescue,
        "improves_over_doing_nothing": improves,
        "peak_without_action_c": (
            round(no_action_peak, 3) if no_action_peak is not None else None
        ),
        "cumulative_setpoint_drift_c": round(drift_up, 3),
        "setpoint_steps": setpoint_steps,
        "history_actions": len(past),
        "source": action.source,
        "requested_by": action.requested_by,
        "horizon_min": horizon_min,
        "effective_horizon_min": effective_horizon,
        "horizon_capped": horizon_capped,
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
