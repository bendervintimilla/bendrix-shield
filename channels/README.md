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
  firma como `whatsapp-app-secret`. **Hoy no existen en el vault**, así
  que el canal corre en modo simulador: los salientes quedan en
  `outbox`, `simulated_click_payload` genera el payload tal como lo
  enviaría Meta, y el panel web es el canal operativo. Cuando existan
  las credenciales, el mismo código envía por Graph API sin cambios en
  el flujo de aprobación.
- Ningún secreto se loguea: solo ids de aprobación y de mensaje.

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
