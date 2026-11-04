"""Presets de equipos de frío: parámetros simulados y setpoint de fábrica.

Valores ROTULADOS como supuestos de orden de magnitud para equipos
chicos típicos; no son mediciones de un equipo real ni cifras de un
fabricante. Sirven para simular (``simulated``) antes de actuar.

- ``FREEZER_PARAMS``: congelador a -18 °C; el producto congelado se
  considera comprometido sobre -15 °C. Es el equipo del ataque real
  del 2-nov en Europa: deshielo forzado a distancia (ver ORDENES.md).
- ``CHILLER_PARAMS``: chiller/vitrina de bebidas a 2 °C, con más
  pérdidas por vidrio y aperturas que una cámara cerrada.
- La cámara por defecto del contrato (``ColdRoomParams()``) queda como
  tercer equipo: setpoint de fábrica 3 °C.
"""

from __future__ import annotations

from shield.physics.contract import ColdRoomParams

# Setpoint de fábrica por nombre de equipo (°C). Supuesto rotulado:
# -18 °C es el estándar habitual de conservación de congelados y 2–3 °C
# el de refrigeración de frescos/bebidas.
FACTORY_SETPOINT_C: dict[str, float] = {
    "camara": 3.0,
    "congelador": -18.0,
    "chiller": 2.0,
}

FREEZER_PARAMS = ColdRoomParams(
    name="congelador",
    ambient_c=25.0,
    ua_wall_w_per_k=18.0,  # mejor aislado que una cámara de frescos
    ua_door_open_w_per_k=150.0,
    air_mass_j_per_k=80_000.0,
    product_cp_j_per_kgk=2_000.0,  # congelado ~2 kJ/kgK (supuesto)
    ha_air_product_w_per_k=35.0,
    cooling_capacity_w=1_800.0,  # debe vencer ~18 W/K × 43 K de salto
    defrost_heater_w=1_200.0,
    hysteresis_c=2.0,
    safe_max_c=-15.0,  # sobre esto el congelado pierde la cadena
    safe_min_c=-30.0,
    max_minutes_above=30.0,
)

CHILLER_PARAMS = ColdRoomParams(
    name="chiller",
    ambient_c=25.0,
    ua_wall_w_per_k=35.0,  # vitrina con vidrio: más pérdida que cámara
    ua_door_open_w_per_k=220.0,
    air_mass_j_per_k=40_000.0,  # equipo chico, poco aire/estructura
    product_cp_j_per_kgk=3_900.0,  # bebidas ~ agua (supuesto)
    ha_air_product_w_per_k=50.0,
    cooling_capacity_w=900.0,
    defrost_heater_w=400.0,
    hysteresis_c=1.0,
    safe_max_c=5.0,
    safe_min_c=0.0,  # bebidas no deben congelarse
    max_minutes_above=30.0,
)
