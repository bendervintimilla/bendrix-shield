# Autopilot bench — SIMULACIÓN (M10)

Basado en los ataques reales de `ORDENES.md`. Alcances: `actor`, `app` (solo esa app y ese tipo de operación), `campaign` (una campaña en 2 apps: actor + proveedor + beneficiarios nuevos) y `global` (solo >=3 apps o varios actores; las operaciones humanas recurrentes a beneficiarios conocidos siguen aun en global). Fondo: 300 escrituras legítimas por escenario, semilla fija 20261104.

| Escenario | Nivel | Breaker global | ms local | Ataques que pasan (sin escudo → wAIrrior) | Legítimas de fondo OK (suspender-todo → wAIrrior) /300 |
|---|---|---|---|---|---|
| defrost_forced_2nov | app | False | 11.498 | 1 → 0 | 0 → 300 |
| arkea_iban_fraud_4nov | campaign | False | 0.092 | 2 → 0 | 0 → 263 |
| stolen_token_oct | app | False | 0.127 | 12 → 0 | 0 → 300 |
| legit_recurring_payment | none | False | 0.034 | 0 → 0 | 0 → 300 |
| legit_scheduled_defrost | none | False | 1.604 | 0 → 0 | 0 → 300 |
| combined_wave | global | True | 4.166 | 15 → 0 | 0 → 38 |

## Ola combinada (único caso global): aviso completo al dueño

> EN: wAIrrior stopped an attack at 10:00.
Cold room: a 4-hour defrost would have spoiled your stock (product to 16.4 °C); we kept it at its last safe setting, 3 °C.
Payments: a payment of 9,000 to a new IBAN for Acme is on hold; Acme's bank details are frozen.
One AI agent's key was stolen; we replaced it.
Other agent writes are paused; your usual human payments to known suppliers keep working.
Tap to undo · Approve the IBAN change only with your second factor.

> ES: wAIrrior detuvo un ataque a las 10:00.
Cámara de frío: un deshielo de 4 horas habría dañado tu stock (producto a 16.4 °C); quedó en su último estado seguro a 3 °C.
Pagos: un pago de 9,000 a un IBAN nuevo para Acme está retenido; los datos bancarios de Acme están congelados.
Una llave de un agente de IA fue robada; ya la reemplazamos.
Las demás escrituras de agentes están en pausa; tus pagos humanos habituales a proveedores conocidos siguen.
Toca para deshacer · Aprueba el cambio de IBAN solo con tu segundo factor.

Lectura: Arkéa es nivel campaign (no global): 263/300 legítimas vivas; las 37 pausadas son los pagos de agente del bot contenido (congelado en físico y pagos tras la contención, ronda 3 de M7: cambiar target o clase de acción ya no evade). Solo la ola en >=3 apps llega a global, y aun ahí sobreviven las operaciones humanas recurrentes (38/300). Cada medida tiene undo y lo irreversible queda para el dueño.

Ronda 3 (M7): C3-11 (otro target) y C3-12 (otra clase de acción) quedan bloqueados por el congelamiento del actor/token; C3-13 (90 min, actores/tokens distintos) correlaciona por objetivo y firma de campaña en 24 h; C3-16 (actor 'wairrior-autopilot' forjado) se marca sospechoso y nunca obtiene rescate. La contención física usa el RescueGrant real de M1 (issue_last_safe_action + verify_action con grant): rescate allow solo con grant firmado válido, de un solo uso. El veredicto por evento ya lleva estado e historia del equipo (24 h): deshielos programados de 40 min repetidos suman finding defrost_pattern sobre el calendario normal.
