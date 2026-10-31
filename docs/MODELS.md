# Models — rutas y campos reales de la Meta Model API

Leído de la documentación oficial el **28-oct-2026**. Nada aquí es adivinado:
cada ruta sale de la página citada. Si una ruta cambia, se corrige aquí primero.

## Base y autenticación

- Base URL: `https://api.meta.ai/v1` ([Quickstart](https://dev.meta.ai/docs/quickstart)).
- Auth: `Authorization: Bearer <llave>`. El SDK de OpenAI no lee `MODEL_API_KEY`
  solo: hay que pasar `api_key` explícito o usar `OPENAI_API_KEY`.
- En este repo la variable canónica es `META_MODEL_API_KEY`;
  `meta_client` también acepta `MODEL_API_KEY` por compatibilidad con la doc.

## Endpoints usados por Shield

| Uso | Método y ruta | Modelo | Fuente |
|---|---|---|---|
| Texto / agentes | `POST /v1/responses` | `muse-spark-1.3`, `muse-wonder-1.0` | [Responses](https://dev.meta.ai/docs/protocols/responses), [Quickstart](https://dev.meta.ai/docs/quickstart) |
| Texto compatible OpenAI | `POST /v1/chat/completions` | `muse-spark-1.3` | [Chat Completions](https://dev.meta.ai/docs/protocols/chat-completions) |
| Voz a texto (archivo) | `POST /v1/asr/transcribe` (multipart) | `muse-voice-transcribe-1.0` | [Speech to text](https://dev.meta.ai/docs/speech-to-text) |
| Voz a texto (vivo) | `wss://api.meta.ai/v1/asr/realtime` | `muse-voice-transcribe-1.0` | [Speech to text](https://dev.meta.ai/docs/speech-to-text) |
| Segmentación | `POST /v1/responses` | `sam-3.1` | [SAM overview](https://dev.meta.ai/docs/sam/overview) |

Notas de campo verificadas:

- **Responses**: el cuerpo lleva `model` e `input` (texto o arreglo de ítems
  tipados: `input_text`, `input_image`, `input_file`, `input_video`). La
  respuesta trae `output[]` con ítems `message`/`reasoning` y
  `usage{input_tokens, output_tokens, total_tokens}`. `previous_response_id`
  continúa la conversación con historia en el servidor.
- **Chat Completions**: el cuerpo lleva `model` y `messages[]` con roles
  `developer`/`system`/`user`/`assistant`/`tool`. `reasoning_effort: "none"`
  devuelve 400 en Muse Spark (siempre razona). Structured output va con
  `response_format` (no con `text.format`, que es de Responses).
- **SAM 3.1**: va por Responses con un mensaje de usuario que trae
  `input_text` (frase corta, un concepto por pedido) más `input_image` o
  `input_video`. La salida llega en el canal `output_text` como texto con
  tokens especiales (`<|box;…|><|mask;…|>`); cero coincidencias es un resultado
  válido (texto vacío). Con `stream: true` los eventos llegan hasta
  `response.completed`.
- **Voice Transcribe (archivo)**: multipart con dos partes: `request` (JSON con
  `mode`, `model`, `audioEncoding`) y `audio` (WAV mono PCM 16-bit a 16 o
  24 kHz, máximo 10 min y 32 MB). Modos: `PUSH_TO_TALK` (default),
  `ENDPOINTING`, `DIARIZATION`. La respuesta JSON trae `sessionId`,
  `transcript`, `audioDurationMs` y `turns[]`. En realtime la autenticación va
  en el frame de handshake (`authorization.accessToken`), no en el header HTTP.

## Modelos y precios (Standard, 28-oct-2026)

Fuente: [Pricing and rate limits](https://dev.meta.ai/docs/pricing-rate-limits).

| Modelo | Entrada /1M | Caché /1M | Salida /1M | Otra unidad |
|---|---|---|---|---|
| `muse-wonder-1.0` | $4.00 | $0.20 | $20.00 | — |
| `muse-spark-1.3` / `1.2` / `1.1` | $1.25 | $0.15 | $4.25 | — |
| `muse-spark-1.3-contributor` | $0.10 | $0.002 | $0.20 | no usado en este repo |
| `muse-image-1.0` | — | — | — | $0.01 por imagen |
| `muse-voice-transcribe-1.0` | — | — | — | $0.18 por hora de audio |
| `sam-3.1` | — | — | — | $2.50 / 1.000 imágenes · $0.20 / 1.000 frames |

Contexto: Wonder y Spark tienen ventana de 1.048.576 tokens
([Models](https://dev.meta.ai/docs/models)).

## Límites y reintentos

| Modelo | RPM | TPM | Otro |
|---|---|---|---|
| `muse-wonder-1.0`, `muse-spark-1.3/1.2/1.1` | 3.000 | 4.000.000 | — |
| `sam-3.1` | 3.000 | — | facturado por imagen/frame |
| `muse-voice-transcribe-1.0` | — | — | 256 streams concurrentes; 16.000 streams/hora |

Ante `429`: backoff exponencial con jitter (base 500 ms, duplicando) y respetar
`Retry-After` si viene. Headers útiles: `x-ratelimit-limit-tokens`,
`x-ratelimit-remaining-tokens`, `x-ratelimit-limit-requests`,
`x-ratelimit-remaining-requests`. Esto ya lo hace `shield/meta_client.py`.

## Errores que el humo trata como `needs_credits`

`401` (llave inválida o ausente), `402` y `403` (sin tarjeta o sin créditos).
En ese caso `make smoke` marca cada llamada como `needs_credits` y termina en
verde: la demo y los tests siguen con replay o fixtures sintéticos.
