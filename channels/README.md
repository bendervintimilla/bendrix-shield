# channels/

Canales con el dueño. Un solo camino de aprobación: el guardián
propone un plan, `ask_owner` lo registra en el `PendingRegistry` vía
`channels/approvals.py:ApprovalBroker`, y el `approval_id` resultante es
el que consumen los runbooks. WhatsApp, voz y panel solo recogen
la decisión; ninguno inventa su propio id.

## WhatsApp (`whatsapp.py`)

- Webhook: `GET /webhook/whatsapp` de verificación
  (`hub.mode`/`hub.verify_token`/`hub.challenge`) y `POST` firmado con
  `X-Hub-Signature-256` (HMAC-SHA256 con el secreto de la app).
- Mensajes interactivos con botones «Aprobar», «Rechazar» y «Ver detalle»
  (ids `approve:<approval_id>`, `reject:<approval_id>`,
  `detail:<approval_id>`), idempotentes por `message_id`: repetir el
  mismo mensaje devuelve `duplicate` sin re-aprobar.
- El número y el token de prueba salen del vault como `whatsapp-test-*`
  (`whatsapp-test-phone`, `whatsapp-test-token`,
  `whatsapp-test-verify-token`, `whatsapp-test-phone-id`) y el secreto de
  firma como `whatsapp-app-secret`, o de las variables de entorno
  equivalentes. Sin credenciales reales el canal corre en modo
  simulador: los salientes quedan en `outbox`,
  `simulated_click_payload` genera el payload tal como lo enviaría
  Meta, y el panel web es el canal operativo.
- Ningún secreto se loguea: solo ids de aprobación y de mensaje.

## Aprobación por nota de voz de WhatsApp en la cadena live

- Al terminar `step_guardian` con plan en modo live (`make live`,
  página `/live`), el panel envía al número del dueño
  (`whatsapp-test-phone`) un texto corto en inglés con el resumen del
  plan y «Reply with a voice note: “yes, rotate it” / “no”». Sin
  credenciales reales el mensaje queda en `outbox` (simulador).
- Una nota de voz entrante (`type: audio` o `voice`) en
  `/webhook/whatsapp` solo se procesa si `from` es el número del dueño
  configurado; cualquier otro número queda `ignored` y no se descarga
  nada. En modo live/con credenciales la firma
  `X-Hub-Signature-256` es obligatoria: sin `whatsapp-app-secret` el
  `POST` se rechaza.
- El media se descarga con Graph API (`GET /{media_id}` y luego la
  `url` devuelta, con Bearer). El dominio de esa URL debe ser de Meta
  (`lookaside.fbsbx.com`, `*.whatsapp.net` o `*.fbcdn.net`) y el
  tamaño máximo es 5 MB. El OGG/Opus se convierte a WAV 16 kHz mono
  con `ffmpeg` y se entrega a `LiveChain.step_voice(wav_bytes=...)`,
  que transcribe por el gateway. Es idempotente por `message_id`:
  los reintentos de Meta no transcriben dos veces.
- La respuesta por WhatsApp incluye la transcripción y lo entendido.
  Si la intención es parcial y pide confirmación, se pide responder
  «confirm»; un texto `confirm` del mismo número llama a
  `step_voice_confirm`. Si queda aprobado, se corre la contención
  (`step_contain`, el mismo paso que dispara el panel) y se responde
  con el resultado (atacante, secuencia SDK y segundos).
- El webhook responde `200` rápido y procesa en un hilo de fondo
  (con lock), para que Meta no reintente por lentitud. En el estado
  de `/live` la voz queda marcada con `voice.channel = "whatsapp"` (o
  `"browser"` si vino del micrófono) y la página muestra la
  transcripción en el mismo sitio de siempre.
- Estado: implementado y probado offline (sin red, con cliente HTTP
  falso y `ffmpeg` real en `tests/test_whatsapp_live_voice.py`).
  La prueba en vivo con Meta queda pendiente; no se ha hecho ninguna
  llamada real a la API de Meta desde este código en las pruebas.

## Cómo configurarlo (Meta for Developers)

1. En [Meta for Developers](https://developers.facebook.com/) crear
   (o usar) una app y agregarle el producto **WhatsApp**.
2. En WhatsApp → Configuración de la API, tomar el **número de
   prueba** y registrar el número del dueño como destinatario
   permitido del número de prueba.
3. Exponer el panel con un túnel HTTPS y configurar el webhook con
   URL `https://<túnel>/webhook/whatsapp`, el verify token elegido y
   la suscripción al campo **`messages`**.
4. Guardar en el vault (nunca en git) los secretos:
   `whatsapp-test-token`, `whatsapp-test-phone-id`,
   `whatsapp-test-phone` (número del dueño, solo dígitos con código
   de país), `whatsapp-test-verify-token` y `whatsapp-app-secret`.
   Como respaldo se leen del entorno `WHATSAPP_TEST_TOKEN`,
   `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_TEST_PHONE`,
   `WHATSAPP_VERIFY_TOKEN` y `WHATSAPP_APP_SECRET`.
5. Arrancar con `make live` y abrir `/live`. La verificación en vivo
   la hace el director con sus credenciales; las pruebas del repo
   son offline.

## Voz (`voice.py`)

- Nota de voz → `MetaClient.transcribe_file` (Muse Voice Transcribe,
  `POST /v1/asr/transcribe` documentado en `docs/MODELS.md`). Sin
  créditos devuelve `needs_credits` y no inventa transcripción.
- La orden la interpreta Spark 1.3 si hay cliente; sin créditos cae al
  parser determinista en español (`parse_voice_command`).
- «sí, rota todo menos Stripe» es una aprobación parcial: excluye los
  pasos cuyo objetivo menciona Stripe. Toda parcial exige confirmación
  (`confirmation_required` → `confirm`) antes de aprobar nada.
- `VoiceApprover` conecta la voz con el guardián: con la confirmación
  dada, `run_once` ejecuta solo los pasos aprobados y marca el resto
  como `skipped`.

## Guardián conectado

`shield/agent.py:RunbookGuardianActions` implementa la interfaz
`GuardianActions` sobre los runbooks reales de
`shield/actions/` (plan → apply con `approval_id` → verify). El flujo
de la demo queda en un solo camino: aviso/anomalía → guardián →
`ask_owner` (WhatsApp, voz o panel) → `approval_id` → runbook →
`verify` → el atacante recibe 401. El E2E está en
`tests/test_channels_web_h8.py`.
