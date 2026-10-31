# web/

Panel del dueño: FastAPI en una página, sin build y sin recursos
externos. Todo el CSS y el JS van inline en `web/app.py`; la página
funciona sin red (en replay) y sin JavaScript los formularios siguen
funcionando por POST normal.

- Franja oscura con la frase del incidente según la fase real
  (`pending`, `awaiting_confirmation`, `contained`, `rejected`,
  `not_rotated`), el detalle traducido de la anomalía (por tipo:
  `new_country`, `new_model`, `cost_spike`), la tira de intentos del
  token robado con los códigos reales y el reloj medido de esta corrida
  (frente a las ~16 h del incidente real).
- Decisión del dueño justo debajo: plan en lenguaje llano (qué, sobre
  quién y por qué), Approve/Reject, nota de voz con su aviso
  (`confirmation_required`, `unknown_command`, `not_pending`,
  `nothing_to_confirm`, `cancelled`) y, cuando ya no hay pendiente,
  el resumen de lo ejecutado con el estado real de cada paso.
- Warehouse (bodega) y Attacker lado a lado, con las tiras reales de
  `agent_statuses` y `attacker_timeline`; Purchasing (compras) debajo,
  con su último estado real.
- Tabla de agentes (nombre, app, estado, modelos y `token_id` corto;
  nunca el token) y feed de decisiones de la política.
- Tira «Where Meta models run» con la función y la etiqueta honesta de
  cada modelo. Las cifras salen de `evals/report.md` y la corrida en
  vivo de Spark Open sigue pendiente (sin llave).
- Pie con el aviso de marca de `docs/brand/README.md`.

## Idioma

Inglés por defecto. Español con `?lang=es`; queda guardado en la
cookie `panel_lang`. El diccionario es `T = {"en": ..., "es": ...}` en
`web/app.py`. El nombre del producto vive en las constantes `BRAND`
y `SUBTITLE`: cambiarlas no toca nada más.

## En vivo sin recargar

- El JS propio (menos de 120 líneas, sin dependencias) intercepta los
  formularios con `fetch` y la cabecera `X-Panel-Fetch: 1`, y
  reemplaza solo `#app`.
- Sondeo cada 2 s a `/panel/live?v=<versión>`: un 204 no toca nada;
  al reemplazar se conserva el texto y el foco del campo de voz si el
  usuario está escribiendo. Se pausa con la pestaña oculta.
- El atacante reintenta solo con POST a `/panel/tick` cada 4 s
  mientras `#app` tenga `data-autotick="1"`. El servidor decide:
  hasta 12 ticks en pendiente desde el último cambio y 3 más tras
  contener; después `DemoState.tick()` no sondea más.
- El reloj sale del servidor y el JS solo lo avanza entre refrescos
  cuando `clock_running` es verdadero.

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
