"""Contrato común de wAIrrior Frontier: verificar antes de actuar.

Un agente de IA (Muse Spark) propone una acción sobre un sistema físico
(cámara de frío, congelador). Antes de ejecutarla, el escudo simula su
consecuencia física con un gemelo térmico y decide allow / ask_owner / block
según si la trayectoria predicha del PRODUCTO sale de la envolvente segura.

La decisión no depende del texto que convenció al agente (inyección, voz,
documento): depende de la física. Por eso una orden inyectada, una deriva
lenta de setpoints «dentro de rango» o un apagado en hora pico se frenan
aunque cada paso parezca inocente.

Este archivo es la ÚNICA interfaz compartida entre los frentes M1..M9.
No cambiar firmas sin avisar al orquestador (ver docs/FRONTIER-PLAN.md).
Todo es determinista, sin red y sin numpy (solo stdlib).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ActionKind = Literal[
    "set_setpoint",  # value = nuevo setpoint °C, duración = hasta nueva orden
    "compressor_off",  # value ignorado, duration_min = minutos apagado
    "defrost",  # ciclo de deshielo: calefactor on, compresor off, duration_min
    "door_open",  # puerta abierta (carga/descarga), duration_min
    "load_product",  # value = kg de producto que entra a ambient_c
]
VerdictKind = Literal["allow", "ask_owner", "block"]


@dataclass(frozen=True)
class ColdRoomParams:
    """Parámetros de un modelo térmico de dos nodos (aire + producto).

    Valores por defecto: supuestos de orden de magnitud para una cámara
    pequeña de restaurante (~10 m3). Están ROTULADOS como supuestos; no son
    mediciones de un equipo real.
    """

    name: str = "camara"
    ambient_c: float = 25.0
    ua_wall_w_per_k: float = 25.0  # conductancia paredes
    ua_door_open_w_per_k: float = 180.0  # infiltración extra con puerta abierta
    air_mass_j_per_k: float = 60_000.0  # aire + estructura liviana
    product_cp_j_per_kgk: float = 3_600.0  # alimentos frescos ~3.6 kJ/kgK
    ha_air_product_w_per_k: float = 40.0  # acople aire-producto (por 100 kg)
    cooling_capacity_w: float = 1_400.0
    defrost_heater_w: float = 800.0
    hysteresis_c: float = 1.0  # termostato on/off alrededor del setpoint
    safe_max_c: float = 5.0  # límite del PRODUCTO (refrigerado)
    safe_min_c: float = -1.0  # por debajo se congela lo fresco
    max_minutes_above: float = 30.0  # tolerancia acumulada sobre safe_max_c


@dataclass
class RoomState:
    t_min: float = 0.0
    air_c: float = 3.0
    product_c: float = 3.0
    product_kg: float = 200.0
    setpoint_c: float = 3.0
    compressor_on: bool = False
    door_open: bool = False
    minutes_above_so_far: float = 0.0


@dataclass(frozen=True)
class ProposedAction:
    kind: ActionKind
    equipment: str = "camara"
    value: float | None = None
    duration_min: float = 0.0
    start_in_min: float = 0.0
    requested_by: str = "refrigeracion"  # agente que lo pide
    source: str = "agent"  # agent | document | voice | schedule | attacker
    note: str = ""


@dataclass
class Trajectory:
    t_min: list[float] = field(default_factory=list)
    air_c: list[float] = field(default_factory=list)
    product_c: list[float] = field(default_factory=list)
    compressor_on: list[bool] = field(default_factory=list)

    def public(self, every: int = 1) -> dict[str, Any]:
        return {
            "t_min": self.t_min[::every],
            "air_c": [round(x, 3) for x in self.air_c[::every]],
            "product_c": [round(x, 3) for x in self.product_c[::every]],
        }


@dataclass
class PhysicalVerdict:
    decision: VerdictKind
    reason: str
    predicted_breach_min: float | None  # minutos hasta que el PRODUCTO pasa safe_max_c
    peak_product_c: float
    minutes_above_limit: float
    baseline: Trajectory
    with_action: Trajectory
    evidence: dict[str, Any] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "predicted_breach_min": self.predicted_breach_min,
            "peak_product_c": round(self.peak_product_c, 3),
            "minutes_above_limit": round(self.minutes_above_limit, 2),
            "evidence": self.evidence,
        }


# ---- Firmas que implementa M1 en shield/physics/thermal.py y gate.py ----
#
# thermal.simulate(params: ColdRoomParams, state: RoomState,
#                  actions: list[ProposedAction], horizon_min: float = 240,
#                  dt_s: float = 30) -> Trajectory
#
# gate.verify_action(params: ColdRoomParams, state: RoomState,
#                    action: ProposedAction,
#                    history: list[ProposedAction] | None = None,
#                    horizon_min: float = 240) -> PhysicalVerdict
#   - history: acciones ya aceptadas en la ventana reciente; se simulan
#     junto con la nueva para atrapar derivas lentas (salami).
#   - block: el producto supera safe_max_c más de max_minutes_above, o baja
#     de safe_min_c, dentro del horizonte.
#   - ask_owner: no rompe la envolvente pero reduce el margen (pico a menos
#     de 1 °C de safe_max_c, o acción de fuente no confiable).
#   - allow: el resto.
#
# residual.check_sensor(params, state_history, reported: list[float]) ->
#   dict  (M7: detecta lecturas de sensor físicamente imposibles = spoofing)
