"""Pipeline verificar-antes-de-actuar (M6, tarea 2: cierra RT-18).

El gate de M1 confía en el RoomState que le pasan: con un sensor
falsificado que reporta 3 °C, una subida «suave» a 4.5 °C quedaba en
ask_owner con el producto real en 6.2 °C (RT-18 del red team). Este
pipeline pone el detector de residuo aguas arriba y FALLA CERRADO:

1. ``residual.check_sensor``: si el sensor miente (spoofed), el estado se
   corrige con la predicción física (aire y producto del gemelo, no la
   lectura falsa) y la decisión final es ``block``, salvo que la acción
   reduzca el riesgo (bajar el setpoint, o cancelar deshielo/apagado/
   apertura con duración 0), caso en el que escala a ``ask_owner``: con
   el sensor en duda, ni lo mitigante se ejecuta sin el dueño.
2. Percepción SAM (M3, opcional): ``product_kg`` y ``door_open`` de la
   cámara mandan sobre el estado reportado (solo se afirma la puerta si
   fue visible; si no se vio, se conserva el estado previo).
3. ``gate.verify_action`` decide sobre el estado ya corregido.

Sin spoofing, el veredicto del gate pasa tal cual y la percepción solo
actualiza masa/puerta. Todo determinista, sin red; lo simulado se rotula.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from shield.physics.contract import (
    ColdRoomParams,
    PhysicalVerdict,
    ProposedAction,
    RoomState,
)
from shield.physics.gate import verify_action
from shield.physics.residual import _as_state, check_sensor


def _perception_values(perception: Any) -> dict[str, Any] | None:
    """Normaliza percepción SAM (objeto M3, dict public() o dict simple)."""
    if perception is None:
        return None
    if isinstance(perception, dict):
        state = perception.get("state") or {}
        return {
            "product_kg": perception.get("product_kg", state.get("product_kg")),
            "door_open": perception.get("door_open", state.get("door_open")),
            "door_visible": perception.get("door_visible"),
            "box_count": perception.get("box_count"),
        }
    return {
        "product_kg": getattr(perception, "product_kg", None),
        "door_open": getattr(perception, "door_open", None),
        "door_visible": getattr(perception, "door_visible", None),
        "box_count": getattr(perception, "box_count", None),
    }


def _reduces_risk(action: ProposedAction, state: RoomState) -> bool:
    """True si la acción mitiga: baja el setpoint o cancela un riesgo."""
    if action.kind == "set_setpoint" and action.value is not None:
        return float(action.value) < float(state.setpoint_c)
    if action.kind in ("defrost", "compressor_off", "door_open"):
        return float(action.duration_min or 0.0) <= 0.0
    return False


def verify_before_actuate(
    params: ColdRoomParams,
    state_history: list[Any],
    reported: list[float],
    action: ProposedAction,
    history: list[ProposedAction] | None = None,
    perception: Any = None,
) -> PhysicalVerdict:
    """Verifica sensor, corrige estado, aplica percepción y decide.

    Devuelve el PhysicalVerdict del gate sobre el estado corregido, con
    la decisión escalada a block/ask_owner si el sensor está falsificado
    y ``evidence["pipeline"]`` con las capas que actuaron.
    """
    states = [_as_state(s) for s in state_history]
    sensor = check_sensor(params, state_history, reported)
    spoofed = bool(sensor.get("spoofed"))

    perc = _perception_values(perception)
    perc_state = getattr(perception, "state", None) if perception is not None else None

    if states:
        base = replace(states[-1])
    elif isinstance(perc_state, RoomState):
        base = replace(perc_state)
    else:
        base = RoomState()

    corrected = replace(base)
    layers: list[str] = ["residual:spoofed" if spoofed else "residual:ok"]
    state_corrected = False
    if spoofed:
        # La lectura falsa no entra: manda la predicción del gemelo.
        corrected = replace(
            corrected,
            air_c=float(sensor.get("predicted_last_c", corrected.air_c)),
            product_c=float(sensor.get("predicted_product_last_c", corrected.product_c)),
            minutes_above_so_far=float(
                states[0].minutes_above_so_far if states else 0.0
            )
            + float(sensor.get("predicted_minutes_above", 0.0)),
        )
        state_corrected = True
        layers.append("correction:physics-over-sensor")

    perception_applied = False
    if perc is not None:
        if perc.get("product_kg") is not None and float(perc["product_kg"]) > 0:
            corrected = replace(corrected, product_kg=float(perc["product_kg"]))
            perception_applied = True
        # La puerta solo se afirma si la cámara la vio (criterio M3).
        if perc.get("door_open") is not None and perc.get("door_visible") is not False:
            corrected = replace(corrected, door_open=bool(perc["door_open"]))
            perception_applied = True
        if perception_applied:
            layers.append("perception:sam-over-state")

    verdict = verify_action(params, corrected, action, history=history)
    layers.append(f"gate:{verdict.decision}")

    decision = verdict.decision
    fail_closed = False
    mitigates = _reduces_risk(action, corrected)
    if spoofed:
        fail_closed = True
        if mitigates:
            # Lo mitigante va al dueño, no se bloquea por el daño ya hecho;
            # solo se bloquea si la propia mitigación crea otro peligro
            # (p. ej. bajar el setpoint hasta congelar el producto).
            cold_hazard = min(verdict.with_action.product_c) < params.safe_min_c
            decision = "block" if cold_hazard else "ask_owner"
        else:
            decision = "block"
        layers.append("fail_closed:ask_owner" if decision == "ask_owner" else "fail_closed:block")

    if spoofed and decision == "block" and not mitigates:
        reason = (
            f"Sensor falsificado: {sensor.get('explanation', '')} "
            f"Estado corregido por física (aire {corrected.air_c:.1f} °C, "
            f"producto {corrected.product_c:.1f} °C); se bloquea por falla "
            f"cerrada. Gate: {verdict.reason}"
        )
    elif spoofed:
        reason = (
            f"Sensor falsificado: {sensor.get('explanation', '')} "
            f"La acción reduce el riesgo, pero con el sensor en duda decide "
            f"el dueño. Gate: {verdict.reason}"
        )
    else:
        reason = verdict.reason

    evidence = {
        **verdict.evidence,
        "pipeline": {
            "layers": layers,
            "sensor_spoofed": spoofed,
            "sensor": {
                "residual_c": sensor.get("residual_c"),
                "threshold_c": sensor.get("threshold_c"),
                "window_min": sensor.get("window_min"),
                "explanation": sensor.get("explanation"),
                "stuck": sensor.get("stuck"),
                "prediction_source": sensor.get("prediction_source"),
            },
            "state_corrected": state_corrected,
            "corrected_state": {
                "air_c": round(float(corrected.air_c), 3),
                "product_c": round(float(corrected.product_c), 3),
                "product_kg": float(corrected.product_kg),
                "door_open": bool(corrected.door_open),
                "setpoint_c": float(corrected.setpoint_c),
                "minutes_above_so_far": round(float(corrected.minutes_above_so_far), 2),
            },
            "reported_state": {
                "air_c": round(float(base.air_c), 3),
                "product_c": round(float(base.product_c), 3),
                "product_kg": float(base.product_kg),
                "door_open": bool(base.door_open),
            },
            "perception_applied": perception_applied,
            "perception": perc,
            "fail_closed": fail_closed,
            "action_reduces_risk": mitigates if spoofed else None,
            "gate_decision_before_fail_closed": verdict.decision,
            "simulated": True,
        },
    }
    return PhysicalVerdict(
        decision=decision,  # type: ignore[arg-type]
        reason=reason,
        predicted_breach_min=verdict.predicted_breach_min,
        peak_product_c=verdict.peak_product_c,
        minutes_above_limit=verdict.minutes_above_limit,
        baseline=verdict.baseline,
        with_action=verdict.with_action,
        evidence=evidence,
    )
