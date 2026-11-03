"""Dispositivo de Refrigeración (cadena de frío) con token propio.

Motivo (3-nov-2026): en Europa atacantes manipularon a distancia la
refrigeración de supermercados, subieron la temperatura de neveras y
congeladores y se perdió comida. En un restaurante el equivalente es
subir el setpoint de la cámara o del congelador hasta echar a perder
el inventario.

Defensa en este módulo, sin red y determinista:

- **Alcance mínimo:** el token de Refrigeración solo trae
  ``coldchain:read`` y ``coldchain:setpoint:<equipo>``. Un token de
  otro agente (p. ej. Bodega, alcance ``crew``) no puede mover un
  setpoint: falta el alcance y se bloquea antes de tocar el equipo.
- **Detección por reglas del equipo:** setpoint fuera del rango seguro
  del equipo, cambio fuera del horario de operación y origen distinto
  del esperado. Fuera de rango bloquea siempre; una sola señal blanda
  (horario u origen) escala al dueño (``ask_owner``); dos o más
  señales blandas, o cualquier combinación con fuera de rango,
  bloquean.
- **Sin mutación si no hay ``allow``:** el estado del equipo solo
  cambia cuando la evaluación permite. El acceso al gateway sigue
  exigiendo el token Shield del dispositivo (200/401 reales en el
  escenario replay).

Rangos seguros usados (restaurante, cadena de frío):
cámara de refrigeración 0 a 4 °C; congelador -22 a -18 °C.
Horario de operación para cambios: 06:00 a 22:00. Origen esperado: EC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

READ_SCOPE = "coldchain:read"
EXPECTED_COUNTRY = "EC"
DAY_START_HOUR = 6
DAY_END_HOUR = 22


def setpoint_scope(equipment: str) -> str:
    return f"coldchain:setpoint:{equipment}"


@dataclass
class Equipment:
    equipment_id: str
    label: str
    min_c: float
    max_c: float
    setpoint_c: float

    def public(self) -> dict[str, Any]:
        return {
            "equipment": self.equipment_id,
            "label": self.label,
            "safe_range_c": [self.min_c, self.max_c],
            "setpoint_c": self.setpoint_c,
        }


def default_equipment() -> dict[str, Equipment]:
    return {
        "camara": Equipment("camara", "Cámara fría", 0.0, 4.0, 2.0),
        "congelador": Equipment("congelador", "Congelador", -22.0, -18.0, -20.0),
    }


@dataclass
class SetpointRequest:
    equipment: str
    setpoint_c: float
    hour: int = 12
    origin_country: str = EXPECTED_COUNTRY
    origin: str = "panel-local"

    def public(self) -> dict[str, Any]:
        return {
            "equipment": self.equipment,
            "setpoint_c": self.setpoint_c,
            "hour": self.hour,
            "origin_country": self.origin_country,
            "origin": self.origin,
        }


@dataclass
class SetpointEvaluation:
    decision: str  # allow | block | ask_owner
    reasons: list[str] = field(default_factory=list)
    applied: bool = False
    equipment: dict[str, Any] = field(default_factory=dict)
    request: dict[str, Any] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reasons": list(self.reasons),
            "applied": self.applied,
            "equipment": dict(self.equipment),
            "request": dict(self.request),
        }


def evaluate_setpoint(
    request: SetpointRequest, *, scopes: list[str] | tuple[str, ...]
) -> SetpointEvaluation:
    """Evalúa un cambio de setpoint. Pura: no muta ningún equipo."""
    equipment = default_equipment().get(request.equipment)
    base = SetpointEvaluation(decision="block", request=request.public())
    if equipment is None:
        base.reasons = ["unknown_equipment"]
        return base
    base.equipment = equipment.public()
    if setpoint_scope(request.equipment) not in scopes:
        base.reasons = [f"missing_scope:{setpoint_scope(request.equipment)}"]
        return base
    reasons: list[str] = []
    if not (equipment.min_c <= request.setpoint_c <= equipment.max_c):
        reasons.append(
            f"out_of_range:{request.setpoint_c:g}C fuera de "
            f"[{equipment.min_c:g},{equipment.max_c:g}]C"
        )
    soft = 0
    if not (DAY_START_HOUR <= request.hour < DAY_END_HOUR):
        reasons.append(f"off_hours:{request.hour:02d}:00 fuera de 06:00-22:00")
        soft += 1
    if request.origin_country != EXPECTED_COUNTRY:
        reasons.append(f"unexpected_origin:{request.origin_country} (esperado {EXPECTED_COUNTRY})")
        soft += 1
    base.reasons = reasons
    if any(r.startswith("out_of_range") for r in reasons) or soft >= 2:
        base.decision = "block"
    elif soft == 1:
        base.decision = "ask_owner"
    else:
        base.decision = "allow"
    return base


class RefrigeracionAgent:
    """Agente/dispositivo de refrigeración: lee estado y mueve setpoints."""

    agent_name = "refrigeracion"

    def __init__(
        self,
        *,
        scopes: list[str] | tuple[str, ...] | None = None,
        equipment: dict[str, Equipment] | None = None,
    ) -> None:
        self.scopes = list(
            scopes
            if scopes is not None
            else [READ_SCOPE, setpoint_scope("camara"), setpoint_scope("congelador")]
        )
        self.equipment = equipment or default_equipment()
        self.token: str | None = None  # token Shield propio (shd_refrigeracion_...)

    def status(self) -> dict[str, Any]:
        if READ_SCOPE not in self.scopes:
            return {
                "decision": "block",
                "reasons": [f"missing_scope:{READ_SCOPE}"],
                "equipment": [e.public() for e in self.equipment.values()],
            }
        return {
            "decision": "allow",
            "reasons": [],
            "equipment": [e.public() for e in self.equipment.values()],
        }

    # -- herramientas del dispositivo (nombres de la lista P0-1) --------
    def leer_temperatura(self) -> dict[str, Any]:
        """Lectura (read): estado y setpoint actual de cada equipo."""
        return self.status()

    def fijar_setpoint(self, request: SetpointRequest) -> SetpointEvaluation:
        """Escritura (write): pide un setpoint; solo se aplica si allow."""
        return self.request_setpoint(request)

    def request_setpoint(self, request: SetpointRequest) -> SetpointEvaluation:
        # El control del dispositivo es esta evaluación (alcance, rango,
        # horario, origen): no es una tool de LLM y no pasa por las
        # reglas YAML de Compras/Bodega (zona de la Parte 3 del gateway).
        evaluation = evaluate_setpoint(request, scopes=self.scopes)
        device = self.equipment.get(request.equipment)
        if device is not None:
            evaluation.equipment = device.public()
        if evaluation.decision != "allow":
            return evaluation
        assert device is not None  # allow implica equipo conocido
        device.setpoint_c = float(request.setpoint_c)
        evaluation.applied = True
        evaluation.equipment = device.public()
        return evaluation
