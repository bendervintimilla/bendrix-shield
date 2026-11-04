# Autopilot bench — SIMULACIÓN (M10)

Basado en los ataques reales de `ORDENES.md`. Breaker en 3 niveles: `actor` (solo ese token), `app` (solo esa app y ese tipo de operación), `global` (solo correlación del mismo actor/campaña en >=2 apps). Fondo: 300 escrituras legítimas por escenario, semilla fija 20261104.

| Escenario | Nivel | Breaker global | ms local | Ataques que pasan (sin escudo → wAIrrior) | Legítimas de fondo OK (suspender-todo → wAIrrior) /300 |
|---|---|---|---|---|---|
| defrost_forced_2nov | app | False | 7.287 | 1 → 0 | 0 → 300 |
| arkea_iban_fraud_4nov | global | True | 0.076 | 2 → 0 | 0 → 0 |
| stolen_token_oct | app | False | 0.116 | 12 → 0 | 0 → 300 |
| legit_recurring_payment | none | False | 0.02 | 0 → 0 | 0 → 300 |
| legit_scheduled_defrost | none | False | 1.588 | 0 → 0 | 0 → 300 |
| combined_wave | global | True | 2.91 | 15 → 0 | 0 → 0 |

## Ola combinada (único caso global): aviso completo al dueño

> EN: You were attacked. We already did: block_action (cold_room:camara), safe_state (cold_room:camara), block_action (pos_erp:supplier:acme), block_action (payments:supplier:acme), hold_payment (payments:supplier:acme), block_action (ai_gateway:muse-spark-1.3), revoke_tokens (*:campaign-actor), circuit_breaker (*:ai_gateway,cold_room,payments,pos_erp) [scope: global]. Tap to undo / release with your second factor. Waiting for your decision (never automatic): cambio definitivo de IBAN de supplier:acme (requiere tu OK); pagar a supplier:acme (retenido, requiere tu OK).

> ES: Fuiste atacado. Ya hicimos: block_action (cold_room:camara), safe_state (cold_room:camara), block_action (pos_erp:supplier:acme), block_action (payments:supplier:acme), hold_payment (payments:supplier:acme), block_action (ai_gateway:muse-spark-1.3), revoke_tokens (*:campaign-actor), circuit_breaker (*:ai_gateway,cold_room,payments,pos_erp) [alcance: global]. Toca para deshacer / liberar con tu segundo factor. Pendiente de tu decisión (nunca automático): cambio definitivo de IBAN de supplier:acme (requiere tu OK); pagar a supplier:acme (retenido, requiere tu OK).

Lectura: en ataques de una sola app, wAIrrior deja vivas casi todas las escrituras legítimas de fondo y suspender-todo las mata todas. Solo la ola correlacionada en >=2 apps justifica el nivel global; ahí las escrituras se pausan (las lecturas siguen) hasta que el dueño libera con segundo factor. Cada medida tiene undo.
