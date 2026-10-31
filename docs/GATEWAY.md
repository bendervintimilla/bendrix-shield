# Gateway — NoKey

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

## Rotación (demo Black October)

Rotar el token de un agente marca el viejo como `rotated` (401 inmediato) y
emite uno nuevo con el mismo alcance. Los demás agentes ni se enteran: es
ese invariante y está cubierto por tests.
