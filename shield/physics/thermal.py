"""Gemelo térmico de dos nodos (aire + producto) de una cámara de frío.

Modelo simulado — supuestos rotulados, no mediciones de un equipo real:

- Dos capacitancias térmicas: el aire (más la estructura liviana) y el
  producto almacenado (``product_kg * product_cp_j_per_kgk``).
- El aire pierde/gana calor con el exterior por ``ua_wall_w_per_k`` y,
  con la puerta abierta, suma ``ua_door_open_w_per_k`` de infiltración.
- Aire y producto intercambian calor con ``ha_air_product_w_per_k``
  (conductancia efectiva para la carga de referencia; no se escala con
  la masa para mantener el acople de un equipo pequeño típico).
- El compresor es on/off con capacidad fija ``cooling_capacity_w`` y lo
  gobierna un termostato con histéresis: enciende a
  ``setpoint + hysteresis_c/2`` y apaga a ``setpoint - hysteresis_c/2``.
- El deshielo enciende un calefactor de ``defrost_heater_w`` y fuerza el
  compresor apagado; ``compressor_off`` también lo fuerza apagado.
- ``load_product`` mezcla al instante la masa entrante a ``ambient_c``
  con el producto: ``T = (m1*T1 + m2*ambient_c) / (m1 + m2)`` y la masa
  (y su capacitancia) crece desde ese momento.
- Integración RK2 (punto medio) con paso ``dt_s``; los eventos y los
  cambios de control se aplican en la grilla de pasos. Determinista,
  solo stdlib, sin red.
"""

from __future__ import annotations

from shield.physics.contract import (
    ColdRoomParams,
    ProposedAction,
    RoomState,
    Trajectory,
)


def _validate(params: ColdRoomParams, horizon_min: float, dt_s: float) -> None:
    """Valida entradas numéricas mínimas; falla con ValueError claro."""
    if dt_s <= 0:
        raise ValueError("dt_s debe ser positivo")
    if horizon_min < 0:
        raise ValueError("horizon_min no puede ser negativo")
    if params.air_mass_j_per_k <= 0 or params.product_cp_j_per_kgk <= 0:
        raise ValueError("las capacitancias térmicas deben ser positivas")
    if params.cooling_capacity_w < 0 or params.defrost_heater_w < 0:
        raise ValueError("las potencias no pueden ser negativas")


def _active(action: ProposedAction, t_min: float) -> bool:
    """True si la acción está vigente en el instante ``t_min``."""
    if action.kind == "set_setpoint":
        return t_min >= action.start_in_min
    if action.kind == "load_product":
        return False  # es un evento instantáneo, no una ventana
    return action.start_in_min <= t_min < action.start_in_min + max(action.duration_min, 0.0)


def _derivatives(
    params: ColdRoomParams,
    air_c: float,
    product_c: float,
    product_kg: float,
    *,
    door_open: bool,
    compressor_on: bool,
    defrost_on: bool,
) -> tuple[float, float]:
    """Derivadas dT/dt (°C/s) del aire y del producto."""
    ua = params.ua_wall_w_per_k + (params.ua_door_open_w_per_k if door_open else 0.0)
    cooling_w = params.cooling_capacity_w if compressor_on else 0.0
    heater_w = params.defrost_heater_w if defrost_on else 0.0
    exchange_w = params.ha_air_product_w_per_k * (air_c - product_c)
    d_air = (
        ua * (params.ambient_c - air_c) - exchange_w - cooling_w + heater_w
    ) / params.air_mass_j_per_k
    product_capacity = max(product_kg, 0.0) * params.product_cp_j_per_kgk
    d_product = exchange_w / product_capacity if product_capacity > 0 else 0.0
    return d_air, d_product


def simulate(
    params: ColdRoomParams,
    state: RoomState,
    actions: list[ProposedAction],
    horizon_min: float = 240,
    dt_s: float = 30,
) -> Trajectory:
    """Simula la cámara desde ``state`` aplicando ``actions``.

    No muta ``state`` ni ``actions``. La trayectoria incluye el instante
    inicial (t = state.t_min) y un punto por paso hasta cubrir el
    horizonte. Las acciones con ``start_in_min`` en el pasado relativo
    (<= instante actual del paso) ya están vigentes.
    """
    _validate(params, horizon_min, dt_s)
    if state.product_kg <= 0:
        raise ValueError("product_kg debe ser positivo")
    for action in actions:
        if action.kind == "set_setpoint" and action.value is None:
            raise ValueError("set_setpoint requiere value (°C)")
        if action.kind == "load_product" and (action.value is None or action.value <= 0):
            raise ValueError("load_product requiere value (kg) positivo")

    ordered = sorted(enumerate(actions), key=lambda item: (item[1].start_in_min, item[0]))
    sorted_actions = [action for _, action in ordered]

    t_min = float(state.t_min)
    air_c = float(state.air_c)
    product_c = float(state.product_c)
    product_kg = float(state.product_kg)
    setpoint_c = float(state.setpoint_c)
    compressor_on = bool(state.compressor_on)
    base_door_open = bool(state.door_open)

    trajectory = Trajectory(
        t_min=[t_min],
        air_c=[air_c],
        product_c=[product_c],
        compressor_on=[compressor_on],
    )

    steps = int(round(horizon_min * 60.0 / dt_s))
    dt_min = dt_s / 60.0
    applied_loads: set[int] = set()

    for step in range(steps):
        step_start = step * dt_min  # minutos desde el inicio de la simulación

        # Setpoints vigentes: gana el último que ya empezó.
        for action in sorted_actions:
            if action.kind == "set_setpoint" and step_start >= action.start_in_min:
                setpoint_c = float(action.value)  # validado no-None arriba

        # Cargas de producto: evento único al llegar su instante.
        for index, action in enumerate(sorted_actions):
            if (
                action.kind == "load_product"
                and index not in applied_loads
                and step_start >= action.start_in_min
            ):
                incoming_kg = float(action.value)
                product_c = (
                    product_kg * product_c + incoming_kg * params.ambient_c
                ) / (product_kg + incoming_kg)
                product_kg += incoming_kg
                applied_loads.add(index)

        door_open = base_door_open or any(
            _active(action, step_start) for action in sorted_actions if action.kind == "door_open"
        )
        forced_off = any(
            _active(action, step_start)
            for action in sorted_actions
            if action.kind in ("compressor_off", "defrost")
        )
        defrost_on = any(
            _active(action, step_start) for action in sorted_actions if action.kind == "defrost"
        )

        # Termostato con histéresis alrededor del setpoint vigente.
        if forced_off:
            compressor_on = False
        elif air_c >= setpoint_c + params.hysteresis_c / 2.0:
            compressor_on = True
        elif air_c <= setpoint_c - params.hysteresis_c / 2.0:
            compressor_on = False

        # RK2 (punto medio) con los controles fijados al inicio del paso.
        d_air, d_product = _derivatives(
            params,
            air_c,
            product_c,
            product_kg,
            door_open=door_open,
            compressor_on=compressor_on,
            defrost_on=defrost_on,
        )
        mid_air = air_c + d_air * dt_s / 2.0
        mid_product = product_c + d_product * dt_s / 2.0
        d_air, d_product = _derivatives(
            params,
            mid_air,
            mid_product,
            product_kg,
            door_open=door_open,
            compressor_on=compressor_on,
            defrost_on=defrost_on,
        )
        air_c += d_air * dt_s
        product_c += d_product * dt_s
        t_min += dt_min

        trajectory.t_min.append(t_min)
        trajectory.air_c.append(air_c)
        trajectory.product_c.append(product_c)
        trajectory.compressor_on.append(compressor_on)

    return trajectory
