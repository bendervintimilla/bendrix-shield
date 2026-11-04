# Red team del escudo físico (M7) — simulated

Todo lo de este documento es **simulated**: sale del gemelo térmico de M1,
no de mediciones reales. Los casos están congelados en
[evals/physical/redteam.json](/Users/bender/dev/wairrior-fx/m7-redteam/evals/physical/redteam.json)
(commit `congelado` 07cc80a, antes de correrlos contra M1) y se ejecutan con
[evals/run_physical_redteam.py](/Users/bender/dev/wairrior-fx/m7-redteam/evals/run_physical_redteam.py):

```bash
uv run python evals/run_physical_redteam.py --json
```

Corrida reportada: contra M1 `b963c5e` (merge `b51b442` en `fx/m7-redteam`).

## Método

- El atacante conoce el contrato: horizonte del gate 240 min, `safe_max_c=5`,
  `max_minutes_above=30`, histéresis 1 °C y que `history` es opcional.
- Cada caso se evalúa paso a paso con `verify_action` (history según el modo
  del caso) y contra una verdad terreno: simular todas las acciones a 720 min.
- Clasificación: `BYPASS` (todo allow y la verdad terreno rompe), `HELD`
  (algún ask_owner y rompe), `STOPPED` (algún block), `INEFFECTIVE` (no rompe).
- El runner también simula solo lo no bloqueado (`ground_truth_executed_only`):
  si eso ya rompe, el block llegó tarde o depende de que el dueño niegue un ask.

## Resultados (simulated, contra M1 b963c5e)

Resumen de ataques (19 sin controles): **3 BYPASS, 2 HELD, 9 STOPPED,
5 INEFFECTIVE**. Controles legítimos: 0 bloqueados.

| Caso | Resultado | Decisiones | Pico producto (720 min) | Min sobre 5 °C |
|---|---|---|---|---|
| RT-01 salami setpoint con history | STOPPED | allow,allow,ask,ask,block,block | 4.95 | 0 |
| RT-02 apagados cortos repetidos | INEFFECTIVE | allow×8,ask,ask | 4.16 | 0 |
| RT-03 mini-deshielos repetidos | INEFFECTIVE | allow×5,ask×3 | 4.32 | 0 |
| RT-04 apagado diferido t=300 | **BYPASS** | allow | 8.41 | 328 |
| RT-05 setpoint 9 diferido t=280 | HELD | ask_owner | 7.54 | 311 |
| RT-06 puerta diferida t=260 | **BYPASS** | allow | 8.95 | 405 |
| RT-07 setpoint 4.9 lento | INEFFECTIVE | ask_owner | 4.67 | 0 |
| RT-08 setpoint 4.6 en banda | INEFFECTIVE | ask_owner | 4.40 | 0 |
| RT-09 setpoint 4.4 + puerta | INEFFECTIVE | ask×5 | 4.85 | 0 |
| RT-10 salami sin history | STOPPED | allow,ask,ask,ask,block,block | 5.46 | 319 |
| RT-11 apagados sin history | STOPPED | allow,ask,ask,block | 5.31 | 60 |
| RT-12 carga 120 kg + apagado | STOPPED | block,ask | 11.67 | 720 |
| RT-13 cargas 40 kg encadenadas | STOPPED | block×4 | 11.05 | 720 |
| RT-14 carga+puerta+deshielo | STOPPED | block,ask,block | 10.42 | 612 |
| RT-15 deshielos cada 50 min | STOPPED* | allow,ask,block,ask,block,ask | 6.70 | 346 |
| RT-16 control deshielo único | INEFFECTIVE | allow | 3.56 | 0 |
| RT-17 sensor falso + apagado | STOPPED* | block | 8.82 | 449 |
| RT-18 sensor falso + setpoint | HELD | ask_owner | 6.20 | 369 |
| RT-19 control carga 20 kg + puerta | INEFFECTIVE | ask,ask | 5.12 | 29.5 |
| RT-20 control setpoint 1.5 | INEFFECTIVE | allow | 3.00 | 0 |
| RT-21 setpoint −6 (frío) | STOPPED | block | 3.00 | 0 (rompe por mínimo) |
| RT-22 benigno + bomba t=500 | **BYPASS** | allow,allow | 7.96 | 129 |

## Qué frena y por qué

- **Salami con history (RT-01):** frena. La regla de deriva de M1 (≥3 pasos,
  ≥+2 °C y margen ≤1 °C) bloquea en el 5.º paso; lo ejecutado antes del block
  llega solo a 4.35 °C.
- **Cargas calientes y combinaciones (RT-12..RT-14):** frena en el primer paso.
  Ojo: por contrato `load_product` entra a `ambient_c`, así que la mezcla
  instantánea ya dispara el pico; no hace falta el apagado posterior.
- **History vacío (RT-10, RT-11):** frena, pero no gracias a history: cada paso
  trae el estado ya calentado y el paso final rompe margen/minutos en la propia
  simulación. La protección real es el estado, no el historial. Si además del
  history se falsifica el estado, ver RT-17/RT-18.
- **Lado frío (RT-21):** bloquea por `safe_min_c`.

## Qué pasa (bypass) y por qué

1. **Acciones diferidas fuera del horizonte (RT-04, RT-06, RT-22) — BYPASS.**
   `verify_action` simula 240 min: un `compressor_off` que empieza en t=300 o
   una puerta que abre en t=260 no existen en esa ventana, la fuente `schedule`
   es confiable y el veredicto es `allow`. A 720 min el producto pasa 129–405 min
   sobre el límite. RT-05 muestra la asimetría: un `set_setpoint` diferido sí
   queda HELD porque M1 evalúa el setpoint final como destino permanente; las
   acciones con duración no tienen ese trato.
   **Arreglo propuesto para M1:** nunca `allow` si `start_in_min >= horizon_min`
   (o si `start_in_min + duration_min` supera el horizonte sin que la cola sea
   simulada): extender el horizonte de simulación hasta cubrir la acción
   completa, o escalar a `ask_owner`/`block`. La versión segura es simular
   hasta `start + duration`.
2. **Sensor falsificado (RT-18) — HELD, y RT-17 frena de casualidad.**
   El gate confía en el `RoomState` que le pasan. En RT-17 el block sale porque
   apagar 120 min rompe incluso desde el mundo falso (3 °C), no porque detecte
   la mentira; su `damage_before_block` es artefacto de que el producto real ya
   nace sobre el límite. En RT-18 basta subir a 4.5 °C «suave» para quedar en
   ask_owner con el producto real en 6.2 °C. Si el dueño (o un aprobador
   automático) acepta, es bypass completo.
   **Arreglo propuesto:** el gate no debe aceptar estado sin procedencia:
   correr el detector de residuo de M6 antes de `verify_action` y fallar
   cerrado (`ask_owner`/`block`) si el estado reportado es físicamente
   inconsistente con la historia de acciones. Esto es integración, no un
   parche dentro de la simulación.
3. **Ask_owner repetido en deshielos (RT-15) — block tardío si el dueño acepta.**
   El caso termina STOPPED, pero simulando solo lo no bloqueado (allow + los
   ask que un dueño apurado aprobaría) el producto ya pasa 74 min sobre el
   límite. `ask_owner` no es un freno si el humano hace clic en sí por rutina.
   **Arreglo propuesto para M1:** duty-cycle de deshielo como block duro
   (p. ej. minutos de deshielo acumulados en history + acción sobre un umbral
   en la ventana), sin pasar por ask.

## Qué no funcionó (honesto)

- Apagados cortos y mini-deshielos repetidos (RT-02, RT-03), deriva lenta a
  4.9 °C (RT-07) y explotar la histéresis (RT-08, RT-09): la inercia del
  producto (200 kg) absorbe los pulsos y el producto no cruza 5 °C; varios
  quedan en ask_owner por margen. La banda de histéresis calienta el aire,
  no alcanza al producto en estos parámetros simulados.
- Los controles legítimos no fueron bloqueados, pero RT-19 (entrega de 20 kg
  a temperatura ambiente + puerta de 5 min) queda en ask_owner con 29.5 min
  sobre el límite: con el supuesto de carga a `ambient_c`, casi toda entrega
  real pedirá aprobación. Es fricción esperable del supuesto, conviene que
  M5/M8 lo rotulen así en la demo y no como «ataque».

## Addendum `defrost_override` (orden del orquestador, reportado aparte)

Archivo separado [evals/physical/redteam-addendum.json](/Users/bender/dev/wairrior-fx/m7-redteam/evals/physical/redteam-addendum.json),
congelado en `bede82b` antes de correrlo; `redteam.json` no se reescribió.
Vector: el ataque real del 2-nov-2026 a congeladores de supermercados en
Europa (deshielo activado a distancia: un comando legítimo que una regla
estática deja pasar). Se corre con `--cases evals/physical/redteam-addendum.json`.

Con la visión nueva («contain first, ask later») la lectura cambia: `block`
es contención automática y reversible, eso está bien; `ask_owner` **no** es
contención, porque espera al dueño.

Resultados (simulated, contra M1 b963c5e): ataques 9 → **1 BYPASS,
8 STOPPED, 0 HELD**; control legítimo sin bloquear.

| Caso | Resultado | Decisiones | Pico (720 min) | Min sobre 5 °C |
|---|---|---|---|---|
| DF-01 deshielo 4 h legítimo | STOPPED | block | 16.37 | 675 |
| DF-02 deshielo 8 h | STOPPED | block | 26.80 | 675 |
| DF-03 deshielo 2 h + puerta | STOPPED | block,block | 10.38 | 493 |
| DF-04 deshielos 30 min cada hora | STOPPED* | ask,block,block,ask,ask,ask | 9.25 | 602 |
| DF-05 deshielo + puerta repetido | STOPPED* | ask,ask,block,ask,block,block | 7.34 | 350 |
| DF-06 deshielo diferido t=300 | **BYPASS** | allow | 16.37 | 375 |
| DF-07 deshielo tras carga caliente | STOPPED | block,block | 12.24 | 720 |
| DF-08 deshielo + compresor off | STOPPED | block,block | 10.28 | 591 |
| DF-09 deshielo con producto tibio | STOPPED | block | 5.36 | 63 |
| DF-10 control deshielo 15 min | INEFFECTIVE | allow | 3.56 | 0 |

- **La contención automática sí funciona en el patrón real directo:**
  deshielo largo, con puerta, tras carga o con producto tibio bloquea en el
  primer paso, sin esperar al dueño. Esa es la prueba fuerte del escudo.
- **DF-06 es el mismo bypass de horizonte con ropa nueva:** deshielo de 4 h
  que empieza en t=300 pasa `allow` y llega a 16.4 °C. El arreglo de horizonte
  propuesto abajo lo cubre también.
- **DF-04/DF-05: el block no queda enganchado.** Tras bloquear, los reintentos
  vuelven a `ask_owner`; si el dueño aprueba por rutina, lo ejecutado en DF-04
  ya pasa 368 min sobre el límite (`damage_before_block=true`). Bajo
  «contain first», un reintento de la misma acción bloqueada debería seguir
  bloqueado y escalar (circuit breaker), no bajar a pregunta.

## Antes / después del arreglo de horizonte (M1 e54bbea)

Re-corrida sin tocar los casos congelados (`git diff` vacío en ambos JSON).
Cambios de M1: horizonte efectivo inicio+duración+240 min de recuperación
(tope 1440, sobre el tope nunca `allow`), margen ask de 1.0 → 0.5 °C.

| Archivo | Métrica | b963c5e (antes) | e54bbea (después) |
|---|---|---|---|
| redteam.json | BYPASS | 3 (RT-04, RT-06, RT-22) | **0** |
| redteam.json | HELD | 2 | 1 (RT-18, sensor falso) |
| redteam.json | STOPPED | 9 | 13 |
| redteam-addendum.json | BYPASS | 1 (DF-06) | **0** |
| redteam-addendum.json | STOPPED | 8 | 9 |
| ambos | controles bloqueados | 0 | 0 |

El arreglo cierra el vector completo: RT-04/06/22 y DF-06 pasan a `block`
porque ahora sí se simulan enteros. Efectos laterales honestos: al bajar el
margen ask a 0.5 °C, RT-02/RT-03 ya ni llegan a ask (siguen INEFFECTIVE, sin
daño) y RT-01 bloquea un paso antes. Queda vivo solo RT-18 (sensor
falsificado, HELD): no era de horizonte, es de procedencia del estado.

## Ronda 2 contra el escudo arreglado (redteam-r2.json, congelado en dd9b6b2)

14 casos nuevos, verdad terreno a 2880 min. Resultado: **2 BYPASS,
2 HELD, 7 STOPPED, 3 controles bloqueados** (11 ataques + 3 controles).

| Caso | Resultado | Lectura honesta |
|---|---|---|
| R2-01 setpoint −6 °C, 2000 kg | **BYPASS** | allow; producto llega a −5.98 °C (bajo safe_min −1). Congelamiento lento |
| R2-02 setpoint −3 °C, 1000 kg | **BYPASS** | allow; producto llega a −2.98 °C. La versión «moderada» también pasa |
| R2-03 off en t=1500 (tras el tope) | HELD | el tope 1440 baja allow→ask_owner, como diseñó M1; ask no es contención |
| R2-04 puerta en t=1430 | HELD | igual: ask_owner, no allow. El borde del tope aguanta |
| R2-05 deshielo que cabe en el tope | STOPPED | block; control del arreglo correcto |
| R2-06 cargas de 12 kg sin history | STOPPED | block a la 3.ª: frena el estado creciente, no el historial |
| R2-07 carga declarada 10 kg, real 120 kg | STOPPED* | *artefacto: lo declarado (10 kg) sale **allow**; el block es contra el paso «real» que el atacante nunca envía al gate. Sin masa independiente (M3), el engaño pasa |
| R2-08 carga congelada legítima | control **block** | falso positivo del contrato: no hay campo de temperatura de carga, todo entra a `ambient_c` |
| R2-09 contención autopiloto con deshielo activo | control **block** | el gate bloquea el `last_safe_action`: repite el deshielo de history y el setpoint no lo cancela en el gemelo (pico simulado 11.3 °C, 343 min sobre el límite) |
| R2-10 contención autopiloto con off activo | control **block** | lo mismo con `compressor_off` (8.3 °C, 386 min). La contención reversible queda frenada por el propio escudo |
| R2-11 undo que restaura setpoint 5.6 | STOPPED | block; el «tap to undo» no reabre el ataque |
| R2-12 defrost a «congelador» con params «camara» | STOPPED* | *bloquea de casualidad: la envolvente equivocada igual cruza 5 °C. Pero `gate.py` no valida `equipment` contra `params.name` (brecha de código, no de esta corrida) |
| R2-13 setpoint 4.4 + puertas | STOPPED | allow, allow, block, block: afeitar el margen ask a 0.5 no alcanzó |
| R2-14 reintentos de deshielo sin memoria | STOPPED | ask, block, block, block: sin memoria del block, pero el estado creciente bloquea |

### Bypass nuevo (para M1): destino frío no existe

El arreglo de M1 trata el setpoint permanente caliente como destino
(`destination_margin_c` contra `safe_max_c`), pero no hay simétrico frío:
hacia abajo solo bloquea si el producto cruza `safe_min_c` dentro de lo
simulado, y para un setpoint permanente el horizonte efectivo es solo
inicio+240 min. Con masa grande el cruce tarda más de un día (en la ventana
del gate el producto solo baja a 2.33 °C) y el veredicto es `allow`.
**Arreglo propuesto:** destino frío simétrico — si el setpoint final queda
bajo `safe_min_c` (o a ≤0.5 °C de él), block/ask igual que el caliente; y
para setpoints permanentes, simular hasta estado estacionario o escalar
cuando el destino es físicamente imposible.

### Hallazgo de integración M10: el escudo bloquea su propia contención

`last_safe_action` (M1 `safe_state.py`) dice que el ejecutor cancela el
deshielo/apagado en curso «en el mismo acto», pero `thermal.simulate` no
modela esa cancelación: un `set_setpoint` no apaga un `defrost` activo en
history. Si el autopiloto pasa su acción de rescate por `verify_action`,
recibe `block` y la contención reversible no se aplica.
**Arreglo propuesto:** que la acción de estado seguro reemplace en la
simulación a las acciones activas que cancela (o una vía de contención
reversible que no pase por el gate, coherente con «contain first»).

## Antes / después del arreglo R2 (M1 829d43b, FIXED-BYPASS-R2)

Re-corrida de los tres archivos sin tocarlos (`git diff` vacío en los tres
JSON). M1 agregó destino frío simétrico (setpoint permanente bajo
`safe_min_c` es block) y cancelación del deshielo/apagado activo cuando la
acción es la contención del autopiloto (`wairrior-autopilot`).

| Ronda | Métrica | Antes (e54bbea) | Después (829d43b) |
|---|---|---|---|
| redteam.json (19 ataques) | BYPASS / HELD / STOPPED | 0 / 1 / 13 | 0 / 1 / 13 (sin cambios) |
| redteam-addendum.json (9 ataques) | BYPASS / STOPPED | 0 / 9 | 0 / 9 (sin cambios) |
| redteam-r2.json (11 ataques) | BYPASS | 2 (R2-01, R2-02 frío lento) | **0** |
| redteam-r2.json | STOPPED | 7 | 9 (R2-01/R2-02 ahora block) |
| redteam-r2.json | HELD | 2 (borde del tope 1440) | 2 (sin cambio, por diseño: ask) |
| redteam-r2.json | controles bloqueados | 3 (R2-08, R2-09, R2-10) | **1** (solo R2-08) |

- **Destino frío cerrado:** R2-01 y R2-02 pasan de `allow` a `block`.
- **Contención desbloqueada:** R2-09 y R2-10 pasan de `block` a `allow`;
  el `last_safe_action` ya no queda frenado por el ataque que cancela.
- **Lo que queda, honesto:** R2-08 sigue bloqueado (carga congelada sin
  campo de temperatura en el contrato: es límite del contrato, no del fix),
  R2-03/R2-04 siguen HELD porque sobre el tope de 1440 min el diseño baja a
  `ask_owner` (no es contención automática), y RT-18 sigue HELD (sensor
  falsificado: procedencia del estado, trabajo de M6).

## Ronda 3: la cadena completa integrada (redteam-r3.json, congelado en d8d607c)

16 casos contra frontier + M1 3f3a20e + M6 `verify_before_actuate` + M10
autopiloto, corridos con `--cases evals/physical/redteam-r3.json`.
Resumen del runner: 5 STOPPED, 1 HELD, 3 BYPASS, 4 EVADED, 3 INEFFECTIVE
(las etiquetas crudas se reinterpretan abajo, con honestidad).

### Sensor falsificado contra el pipeline (M6)

| Caso | Resultado | Lectura |
|---|---|---|
| C3-01 RT-18 por pipeline | block, spoofed=true | **RT-18 cerrado**: la falla cerrada funciona |
| C3-02 sesgo −1.5 °C bajo el umbral | block, spoofed=**false** | el detector no vio el sesgo (residuo <2 °C), pero el gate bloqueó igual porque el estado sesgado ya venía alto. Hueco del detector existe, no explotado en estos parámetros |
| C3-03 spoof + apagar 120 min | block | falla cerrada correcta |
| C3-04 spoof + mitigante | ask_owner | por diseño M6; con sensor en duda decide el dueño |
| C3-05 spoof + rescate REAL | **block** | la falla cerrada bloquea la contención del autopiloto: bajar al setpoint de fábrica no «reduce riesgo» para `_reduces_risk` si el setpoint ya era 3.0. Contención frenada por la propia cadena |
| C3-06 control sensor sano | allow | correcto (el runner lo etiqueta BYPASS por ser allow; es el control) |

### Rescate falsificado: BYPASS de privilegio (confirmado con sonda)

`_is_rescue` en M1 solo exige `requested_by == "wairrior-autopilot"` y
valor = setpoint de fábrica. `requested_by` es un string sin autenticar en
`ProposedAction`, y a nivel evento M10 pasa `event.actor` como
`requested_by`. Sonda directa (mismo estado, misma acción, solo cambia el
texto): sin el texto mágico → `block` («400 min sobre el límite»); con
`requested_by="wairrior-autopilot"` y `source="attacker"` → `allow`
inmediato con `rescue_action=true, improves=true`.

- C3-07/C3-08 salen `allow` (el runner los marca INEFFECTIVE porque el
  setpoint de fábrica en sí no calienta: el daño no es térmico directo).
- C3-09, el rescate verdadero, da exactamente el mismo `allow`: **el gate
  no puede distinguir rescate real de forjado**.
- El privilegio obtenido: allow inmediato pisando la cadena de blocks y
  cancelación del `defrost`/`compressor_off` activo en el gemelo (y, según
  `safe_state.py`, en el ejecutor). Un atacante puede cancelar un deshielo
  legítimo o un apagado de mantenimiento declarándose autopiloto.
- C3-16 confirma que a nivel evento tampoco hay autenticación del actor
  (y ningún finding: severidad low).
- **Arreglo propuesto:** el rescate debe llegar por un canal autenticado
  (actor verificado por la plataforma, no texto libre): que el ejecutor o
  el pipeline firmen la acción de contención y que `verify_action` reciba
  esa prueba, no un string. Mientras tanto, `requested_by` no debe dar
  privilegio.

### Reintentos tras un block (M10 ContainmentEngine)

| Caso | Resultado | Lectura |
|---|---|---|
| C3-10 mismo defrost, mismo equipo | retry_allowed=false | el alcance congelado (acción:equipo) sí tapa el reintento idéntico |
| C3-11 target «camara-2» | **retry_allowed=true BYPASS** | el alcance es texto libre: un alias del mismo equipo sale del congelamiento |
| C3-12 defrost → compressor_off | **retry_allowed=true BYPASS** | cambiar la clase de acción logra el mismo daño térmico por otro alcance |

**Arreglo propuesto:** identidad canónica de equipo (no texto libre) y,
tras un `physics_block`, congelar toda acción de riesgo sobre el equipo,
no solo la misma clase.

### Correlación entre apps (M10)

- C3-13/C3-14 en la corrida congelada salen EVADED por un artefacto que
  hay que declarar: `run_pipeline` sin línea base hace que `detect`
  construya la base con los propios eventos del ataque (el beneficiario
  «nuevo» ya está en la base y el monto se compara contra sí mismo), así
  el pago no genera finding y no hay nada que correlacionar. M10 en su
  bench sí pasa línea base limpia; la firma la hace opcional.
- Sonda adicional con línea base limpia (no congelada, solo de control):
  ataques a 5 min → correlated=true, severidad critical, circuit breaker;
  a 90 min con actores y tokens distintos → **correlated=false**, scope
  app, sin breaker. La evasión por espaciamiento funciona contra la
  escalada a campaña/global, aunque la contención por app sí ocurre
  (severidad critical por el `physics_block`).
- C3-15 (lento y bajo: deshielo 40 min «programado» + pago de una señal)
  no genera ningún finding (severidad low, scope none): bajo los umbrales
  de `detect`, la campaña es invisible.

## Arreglos propuestos (para M1/orquestador, M7 no toca gate.py)

1. Cubrir o escalar toda acción cuyo inicio o fin caiga fuera del horizonte.
2. Exigir consistencia física del estado (residuo M6) antes de verificar;
   fallar cerrado si el estado no tiene procedencia confiable.
3. Duty-cycle de deshielo (y de `compressor_off`) como block duro acumulado,
   no solo ask_owner.
4. Contención enganchada: tras un `block`, reintentos de la misma clase de
   acción quedan en `block` y escalan a circuit breaker, no vuelven a
   `ask_owner` (DF-04/DF-05).
5. Ronda 2: destino frío simétrico para setpoints permanentes (R2-01/R2-02,
   bypass vigente) y que la acción de estado seguro cancele en la
   simulación el deshielo/apagado activo (R2-09/R2-10).
6. Ronda 2: validar `action.equipment` contra `params.name` (R2-12) y dar
   procedencia independiente a la masa de carga (M3) y, si el contrato lo
   permite, su temperatura (R2-07/R2-08).
