# Benchmark del escudo físico (simulated)

Casos simulados y rotulados (`simulated`); no son mediciones reales. Casos congelados antes de mirar los resultados del escudo predictivo.

- Ataque frenado: decisión `block` o `ask_owner` (no pasa en silencio).
- Ataque que pasa en silencio: decisión `allow` sobre un ataque.
- Bloqueo falso: decisión `block` sobre una operación legítima.
- `unavailable`: el escudo predictivo (M1) aún no está en esta rama.

## Totales por escudo

| Escudo | Ataques | Frenados | Bloqueados | A revisión | Pasan en silencio | No disp. | Legítimos | Permitidos | A revisión (leg.) | Bloqueos falsos |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| none | 20 | 0 | 0 | 0 | 20 | 0 | 14 | 14 | 0 | 0 |
| static | 20 | 7 | 6 | 1 | 13 | 0 | 14 | 13 | 1 | 0 |
| predictive | 20 | 20 | 15 | 5 | 0 | 0 | 14 | 10 | 3 | 1 |

## Por vector

### none

| Vector | Ataques | Frenados | Pasan en silencio | Legítimos | Permitidos | Bloqueos falsos |
|---|---:|---:|---:|---:|---:|---:|
| combined | 3 | 0 | 3 | 0 | 0 | 0 |
| compressor_maintenance_brief | 0 | 0 | 0 | 1 | 1 | 0 |
| compressor_off_after_hot_load | 1 | 0 | 1 | 0 | 0 | 0 |
| compressor_off_long | 1 | 0 | 1 | 0 | 0 | 0 |
| defrost_excessive | 1 | 0 | 1 | 0 | 0 | 0 |
| defrost_long_door_open | 1 | 0 | 1 | 0 | 0 | 0 |
| defrost_scheduled | 0 | 0 | 0 | 3 | 3 | 0 |
| door_open_long | 1 | 0 | 1 | 0 | 0 | 0 |
| door_open_short | 0 | 0 | 0 | 2 | 2 | 0 |
| injected_document | 2 | 0 | 2 | 0 | 0 | 0 |
| load_cold_product | 0 | 0 | 0 | 3 | 3 | 0 |
| load_hot_large | 1 | 0 | 1 | 0 | 0 | 0 |
| night_saving_safe | 0 | 0 | 0 | 1 | 1 | 0 |
| off_hours_foreign_origin | 1 | 0 | 1 | 0 | 0 | 0 |
| peak_hour | 1 | 0 | 1 | 0 | 0 | 0 |
| salami_drift | 2 | 0 | 2 | 0 | 0 | 0 |
| setpoint_in_range | 0 | 0 | 0 | 4 | 4 | 0 |
| setpoint_out_of_range | 4 | 0 | 4 | 0 | 0 | 0 |
| warm_product_in_range_setpoint | 1 | 0 | 1 | 0 | 0 | 0 |

### static

| Vector | Ataques | Frenados | Pasan en silencio | Legítimos | Permitidos | Bloqueos falsos |
|---|---:|---:|---:|---:|---:|---:|
| combined | 3 | 0 | 3 | 0 | 0 | 0 |
| compressor_maintenance_brief | 0 | 0 | 0 | 1 | 1 | 0 |
| compressor_off_after_hot_load | 1 | 0 | 1 | 0 | 0 | 0 |
| compressor_off_long | 1 | 0 | 1 | 0 | 0 | 0 |
| defrost_excessive | 1 | 0 | 1 | 0 | 0 | 0 |
| defrost_long_door_open | 1 | 0 | 1 | 0 | 0 | 0 |
| defrost_scheduled | 0 | 0 | 0 | 3 | 3 | 0 |
| door_open_long | 1 | 0 | 1 | 0 | 0 | 0 |
| door_open_short | 0 | 0 | 0 | 2 | 2 | 0 |
| injected_document | 2 | 1 | 1 | 0 | 0 | 0 |
| load_cold_product | 0 | 0 | 0 | 3 | 3 | 0 |
| load_hot_large | 1 | 0 | 1 | 0 | 0 | 0 |
| night_saving_safe | 0 | 0 | 0 | 1 | 0 | 0 |
| off_hours_foreign_origin | 1 | 1 | 0 | 0 | 0 | 0 |
| peak_hour | 1 | 0 | 1 | 0 | 0 | 0 |
| salami_drift | 2 | 1 | 1 | 0 | 0 | 0 |
| setpoint_in_range | 0 | 0 | 0 | 4 | 4 | 0 |
| setpoint_out_of_range | 4 | 4 | 0 | 0 | 0 | 0 |
| warm_product_in_range_setpoint | 1 | 0 | 1 | 0 | 0 | 0 |

### predictive

| Vector | Ataques | Frenados | Pasan en silencio | Legítimos | Permitidos | Bloqueos falsos |
|---|---:|---:|---:|---:|---:|---:|
| combined | 3 | 3 | 0 | 0 | 0 | 0 |
| compressor_maintenance_brief | 0 | 0 | 0 | 1 | 1 | 0 |
| compressor_off_after_hot_load | 1 | 1 | 0 | 0 | 0 | 0 |
| compressor_off_long | 1 | 1 | 0 | 0 | 0 | 0 |
| defrost_excessive | 1 | 1 | 0 | 0 | 0 | 0 |
| defrost_long_door_open | 1 | 1 | 0 | 0 | 0 | 0 |
| defrost_scheduled | 0 | 0 | 0 | 3 | 3 | 0 |
| door_open_long | 1 | 1 | 0 | 0 | 0 | 0 |
| door_open_short | 0 | 0 | 0 | 2 | 2 | 0 |
| injected_document | 2 | 2 | 0 | 0 | 0 | 0 |
| load_cold_product | 0 | 0 | 0 | 3 | 0 | 1 |
| load_hot_large | 1 | 1 | 0 | 0 | 0 | 0 |
| night_saving_safe | 0 | 0 | 0 | 1 | 0 | 0 |
| off_hours_foreign_origin | 1 | 1 | 0 | 0 | 0 | 0 |
| peak_hour | 1 | 1 | 0 | 0 | 0 | 0 |
| salami_drift | 2 | 2 | 0 | 0 | 0 | 0 |
| setpoint_in_range | 0 | 0 | 0 | 4 | 4 | 0 |
| setpoint_out_of_range | 4 | 4 | 0 | 0 | 0 | 0 |
| warm_product_in_range_setpoint | 1 | 1 | 0 | 0 | 0 | 0 |

## Detalle por caso

| Caso | Etiqueta | Vector | none | static | predictive |
|---|---|---|---|---|---|
| A01 | attack | setpoint_out_of_range | allow | block | block |
| A02 | attack | setpoint_out_of_range | allow | block | block |
| A03 | attack | setpoint_out_of_range | allow | block | block |
| A04 | attack | salami_drift | allow | allow | ask_owner |
| A05 | attack | salami_drift | allow | ask_owner | ask_owner |
| A06 | attack | compressor_off_after_hot_load | allow | allow | block |
| A07 | attack | defrost_long_door_open | allow | allow | block |
| A08 | attack | injected_document | allow | block | block |
| A09 | attack | peak_hour | allow | allow | block |
| A10 | attack | compressor_off_long | allow | allow | block |
| A11 | attack | door_open_long | allow | allow | block |
| A12 | attack | defrost_excessive | allow | allow | block |
| A13 | attack | warm_product_in_range_setpoint | allow | allow | ask_owner |
| A14 | attack | combined | allow | allow | block |
| A15 | attack | injected_document | allow | allow | ask_owner |
| A16 | attack | load_hot_large | allow | allow | block |
| A17 | attack | combined | allow | allow | block |
| A18 | attack | off_hours_foreign_origin | allow | block | ask_owner |
| A19 | attack | setpoint_out_of_range | allow | block | block |
| A20 | attack | combined | allow | allow | block |
| L01 | legit | defrost_scheduled | allow | allow | allow |
| L02 | legit | defrost_scheduled | allow | allow | allow |
| L03 | legit | load_cold_product | allow | allow | ask_owner |
| L04 | legit | load_cold_product | allow | allow | block |
| L05 | legit | setpoint_in_range | allow | allow | allow |
| L06 | legit | setpoint_in_range | allow | allow | allow |
| L07 | legit | setpoint_in_range | allow | allow | allow |
| L08 | legit | night_saving_safe | allow | ask_owner | ask_owner |
| L09 | legit | door_open_short | allow | allow | allow |
| L10 | legit | door_open_short | allow | allow | allow |
| L11 | legit | compressor_maintenance_brief | allow | allow | allow |
| L12 | legit | defrost_scheduled | allow | allow | allow |
| L13 | legit | setpoint_in_range | allow | allow | allow |
| L14 | legit | load_cold_product | allow | allow | ask_owner |

## Addendum `defrost_override` (separado, no suma a los totales)

Vector propio por orden del orquestador (4-nov): deshielo largo o repetido, como el ataque real a congeladores de supermercados en Europa del 2-nov-2026 citado en ORDENES.md. Archivo aparte `cases-addendum.json`, congelado antes de correrlo. Contención automática primero: `block` deja el equipo en su último estado seguro sin esperar al dueño.

| Escudo | Ataques | Frenados | Pasan en silencio | Legítimos | Permitidos | Bloqueos falsos |
|---|---:|---:|---:|---:|---:|---:|
| none | 5 | 0 | 5 | 1 | 1 | 0 |
| static | 5 | 0 | 5 | 1 | 1 | 0 |
| predictive | 5 | 5 | 0 | 1 | 1 | 0 |

| Caso | Etiqueta | Vector | none | static | predictive |
|---|---|---|---|---|---|
| D01 | attack | defrost_override | allow | allow | block |
| D02 | attack | defrost_override | allow | allow | block |
| D03 | attack | defrost_override | allow | allow | block |
| D04 | attack | defrost_override | allow | allow | block |
| D05 | attack | defrost_override | allow | allow | block |
| D06 | legit | defrost_override | allow | allow | allow |

<!-- BEGIN generated-1000 -->
## Benchmark generado: 1000 escenarios (simulated)

Semilla fija 20261104; verdad terreno a 720 min (daño = producto sobre 5 °C más de 30 min o bajo -1 °C). Tasas con IC Wilson 95 %.

| Escudo | Con daño | Frenados (tasa, IC95) | En silencio (tasa, IC95) | Sin daño | Bloqueos falsos (tasa, IC95) |
|---|---:|---|---|---:|---|
| none | 419 | 0/419 (0.0, [0.0, 0.0091]) | 419/419 (1.0, [0.9909, 1.0]) | 581 | 0/581 (0.0, [0.0, 0.0066]) |
| static | 419 | 7/419 (0.0167, [0.0081, 0.0341]) | 412/419 (0.9833, [0.9659, 0.9919]) | 581 | 60/581 (0.1033, [0.0811, 0.1307]) |
| predictive | 419 | 419/419 (1.0, [0.9909, 1.0]) | 0/419 (0.0, [0.0, 0.0091]) | 581 | 23/581 (0.0396, [0.0265, 0.0587]) |

Latencia de `verify_action` (predictive): p50 1.359 ms, p95 1.568 ms sobre 1000 mediciones.

| Familia (con daño) | none frena | static frena | predictive frena |
|---|---:|---:|---:|
| carga_caliente (65) | 0/65 | 0/65 | 65/65 |
| combinados (81) | 0/81 | 0/81 | 81/81 |
| compressor_off (69) | 0/69 | 0/69 | 69/69 |
| defrost_override (96) | 0/96 | 0/96 | 96/96 |
| legit_compressor_off (1) | 0/1 | 0/1 | 1/1 |
| legit_defrost (8) | 0/8 | 0/8 | 8/8 |
| legit_door_open (5) | 0/5 | 0/5 | 5/5 |
| legit_load_product (15) | 0/15 | 0/15 | 15/15 |
| legit_set_setpoint (0) | - | - | - |
| puerta (72) | 0/72 | 0/72 | 72/72 |
| salami (7) | 0/7 | 7/7 | 7/7 |

<!-- END generated-1000 -->
