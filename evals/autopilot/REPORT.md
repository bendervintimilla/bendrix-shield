# Autopilot bench — SIMULACIÓN (M10)

Escenarios basados en los ataques reales citados en `ORDENES.md`. Nada de esto es una medición sobre clientes reales.

| Escenario | Severidad | Breaker | Detección→contención (ms, local) | Maliciosas que pasan sin escudo | Maliciosas bloqueadas wAIrrior | Escrituras legítimas OK (suspender-todo) | Escrituras legítimas OK (wAIrrior) |
|---|---|---|---|---|---|---|---|
| defrost_forced_2nov | critical | True | 7.302 | 1 | 1 | 0 | 0 |
| arkea_iban_fraud_4nov | critical | True | 0.067 | 2 | 2 | 0 | 0 |
| stolen_token_oct | high | False | 0.069 | 12 | 12 | 0 | 2 |
| legit_recurring_payment | low | False | 0.016 | 0 | 0 | 0 | 2 |
| legit_scheduled_defrost | low | False | 1.352 | 0 | 0 | 0 | 1 |

Lectura: suspender todo (patrón Arkéa) frena el ataque pero también todas las operaciones legítimas. wAIrrior contiene por actor/app y solo pausa escrituras cuando salta el circuit breaker (≥2 apps o crítico); las lecturas siguen y cada medida tiene undo. Lo irreversible (pagar, IBAN definitivo) queda para el dueño con segundo factor.
