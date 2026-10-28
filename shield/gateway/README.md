# shield/gateway/

Proxy compatible con OpenAI (`/v1/chat/completions`, `/v1/responses` y
`/v1/audio/transcriptions`; SAM 3.1 va por `/v1/responses` según la doc de
Meta) con streaming SSE. Recibe un token Shield, lo mapea a agente →
proveedor → llave del vault, aplica token/modelo/tope/ritmo + `gate.check`
y registra cada `CallLog`. Detalle y latencia medida: `docs/GATEWAY.md`.
