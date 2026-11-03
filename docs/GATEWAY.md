# Gateway — Wairrior

Proxy compatible con OpenAI. La app presenta su token Shield
(`Authorization: Bearer shd_<agent>_...`); el gateway valida y reenvía a la Meta
Model API con la llave real, que vive solo en el vault. La app nunca ve esa
llave. Arranque local:

```bash
SHIELD_VAULT_BACKEND=keychain uv run python -m shield.gateway.app
# escucha en http://127.0.0.1:8000
```

## Rutas

| Ruta del gateway | Upstream (Meta, docs/MODELS.md) | Notas |
|---|---|---|
| `POST /v1/chat/completions` | `POST /v1/chat/completions` | Streaming SSE con `stream: true` |
| `POST /v1/responses` | `POST /v1/responses` | Por aquí va SAM 3.1 (`model: "sam-3.1"`); la doc de Meta no define una ruta SAM separada |
| `POST /v1/audio/transcriptions` | `POST /v1/asr/transcribe` | Forma OpenAI (multipart `file`+`model`) traducida al multipart de Meta (`request` JSON + `audio`) |
| `GET /health` | — | `{"status":"ok"}` |

## Antes de reenviar (en este orden)

1. **Auth**: token inexistente → `401 invalid_token`; revocado → `401
   revoked_token`; rotado → `401 rotated_token`. Solo se guarda el sha256
   del token en SQLite (`shield/registry.py`).
2. **Modelo permitido** por token (`AgentToken.models`): si no, `403
   model_not_allowed`.
3. **Tope de gasto** (`spend_cap_usd` contra la suma de `CallLog` del
   agente): `403 spend_cap_exceeded`.
4. **Rate limit** por token (ventana 60 s, 60/min por defecto): `429
   rate_limit_exceeded` con `Retry-After`.
5. **Gate** (`gate.check`): canario → `403 gate_blocked` y alerta; llaves o
   PII en el payload salen redactadas antes de reenviar.
6. Upstream `401/402/403` (sin tarjeta o créditos) → `503 needs_credits`:
   la demo sigue en replay y no se confunde con el token Shield del cliente.

Cada llamada queda en `CallLog` (agente, modelo, tokens, costo según
docs/MODELS.md, latencia, IP y país). El país sale de GeoLite2 si existe una
base local (`SHIELD_GEOLITE_DB` + `maxminddb`); el header `X-Demo-Country`
solo se honra con `SHIELD_SANDBOX=1` (demo), nunca en producción.

La respuesta también pasa por el gate: se redactan llaves/PII y un canario
en la respuesta bloquea con `502 gate_blocked_response` (en streaming, el
bloqueo corta el flujo con un evento de error).

## Vault

`shield/vault/` expone `get/put/fingerprint/last4` con tres backends:
Secret Manager (proyecto de `SHIELD_GCP_PROJECT`, import perezoso), llavero de macOS
(`security` CLI) y memoria (tests). Solo nombre, huella sha256[:8] y
últimos 4 pueden loguearse; el valor jamás.

## Latencia agregada (medida)

Método: `TestClient` contra el gateway con upstream falso instantáneo
(`httpx.MockTransport`), 80 llamadas `chat/completions` en esta Mac.

- p50 extremo a extremo local: **1,74 ms** (p95: 2,48 ms), según `evals/report.md`.

Es el costo agregado de Shield sin red; contra la Meta Model API manda la
latencia del upstream. Reproduce con `Registry.latency_percentile(50)`.

## Endurecimiento C2489-3

Cuatro controles por token (vacío/None = sin restricción, para no romper
tokens anteriores). Se crean con `Registry.create_token(...,
allowed_routes=..., numeric_limits=..., rate_limit_per_minute=...,
require_nonce=...)` y la rotación los conserva.

1. **Alcance mínimo (verbo + ruta + rangos).** `allowed_routes` acepta
   `"POST /v1/chat/completions"`, `"POST:/v1/..."`, `"/v1/..."` y prefijo
   `"POST /v1/*"` (`"*"` = todo). Los scopes con forma de ruta en `scopes`
   cuentan igual; scopes legados sin `/` (p. ej. `"crew"`) no restringen.
   Fuera de alcance: `403 route_not_allowed`. `numeric_limits` mapea campo
   a `[mín, máx]` y se revisa en todo el payload (p. ej.
   `{"setpoint_c": [-25, 5], "temperature": [0, 1]}`): fuera de rango,
   `403 value_out_of_range`. Esto frena el caso de la nevera: un token de
   refrigeración no puede pedir 22 °C ni tocar otra ruta.
2. **Tasa por token.** `rate_limit_per_minute` del token manda sobre el
   global del gateway (60/min): `429 rate_limit_exceeded`.
3. **Anti-repetición.** Con `require_nonce=True` cada pedido exige
   `X-Shield-Nonce` (único por token) y `X-Shield-Timestamp` (segundos,
   ventana ±300 s). Sin ellos: `401 nonce_required`; viejo: `401
   stale_timestamp`; repetido: `409 replay_detected`. Así un setpoint
   capturado no se puede repetir.
4. **Auditoría con cadena de hash + revocación de emergencia.** Cada
   `CallLog` guarda `prev_hash`/`entry_hash` (sha256 encadenado desde
   génesis `"0"*64`); `Registry.verify_audit_chain()` devuelve
   `(False, id)` en la primera fila manipulada. `Registry.revoke_all(
   agent=..., app=...)` revoca en masa y el endpoint
   `POST /shield/revoke-all` (header `X-Shield-Emergency` igual a la
   variable `SHIELD_EMERGENCY_TOKEN`; sin variable, `503`) lo expone
   para apagar todo en segundos.

Pruebas: `tests/test_gateway_hardening_c2489.py` (15 casos, offline).

## Rotación (demo Black October)

Rotar el token de un agente marca el viejo como `rotated` (401 inmediato) y
emite uno nuevo con el mismo alcance. Los demás agentes ni se enteran: es
ese invariante y está cubierto por tests.
