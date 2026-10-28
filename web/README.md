# web/

Panel del dueño (H8): FastAPI + HTMX en una página, sin build pesado.

- Apps y agentes conectados (registro del gateway, sin tokens en claro).
- Flujo en vivo de las decisiones de la política (`CallLog`, con
  refresco HTMX cada 3 s en el fragmento de decisiones).
- Incidentes con anomalías y exposición, plan del guardián y botones
  de aprobación/rechazo: es el plan B de WhatsApp y usa el mismo
  `approval_id` del `PendingRegistry`.
- Formulario de voz: pega la transcripción de la nota («sí, rota todo»)
  y pasa por el mismo flujo de aprobación parcial con confirmación.
- Terminal del atacante con la línea de tiempo `200 → 401` de
  `sandbox/attacker.py`, y cronómetro desde el incidente.
- Incluye el webhook de WhatsApp (`/webhook/whatsapp`) en modo
  simulador mientras el vault no tenga `whatsapp-test-*`.

## Correrlo

```bash
DEMO=replay uv run python -m web.app   # http://127.0.0.1:8001
```

En `DEMO=replay` todo es en memoria: registry `:memory:`, gateway con
upstream falso y token de Bodega usado desde un país nuevo como
incidente semilla. Sin red ni créditos.

Estado JSON para tests o depuración: `GET /panel/state`.

## Corte

La tarjeta visual del incidente con Muse Image (punto opcional de H8)
se cortó: sin créditos no se puede mostrar en vivo y el panel ya
comunica el incidente. Si suma con créditos, va como imagen adjunta al
mensaje de WhatsApp, no como otra página.
