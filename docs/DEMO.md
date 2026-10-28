# Demo de 3:00 — Bendrix Shield (guion del SPEC §4)

Dos modos con los mismos comandos: **replay** (sin red ni créditos, para
ensayar y para el jurado sin depender de la tarjeta) y **en vivo** (con
créditos Meta y la llave de Baseten en el vault). En replay todo lo que
necesite un modelo responde `needs_credits` o sale de la caché por hash, y
la demo no se cae.

## Antes de empezar

```bash
cd ~/dev/bendrix-shield-h9   # o el checkout con este PR ya fusionado
uv sync --extra dev
make test                    # debe terminar en verde
```

Replay (sin red):

```bash
export SHIELD_REPLAY=1
export SHIELD_VAULT_BACKEND=memory
```

En vivo (con créditos):

```bash
unset SHIELD_REPLAY
export SHIELD_VAULT_BACKEND=keychain   # llaves en el llavero de macOS
security find-generic-password -s meta-model-api-key -a hackathon -w >/dev/null \
  && echo "llave Meta presente"        # nunca la imprimas
security find-generic-password -s baseten-api-key -a hackathon -w >/dev/null \
  && echo "llave Baseten presente"     # si falta, Spark Open marca needs_credits
```

## Guion

### 0:00 – 0:20 · Black October (el problema)

Cuenta el incidente: el 21-oct-2026 las llaves de IA fueron el botín
(LiteLLM troyanizado, variables de Railway expuestas, ~16 h de abuso,
USD 310). «Las apps tenían la llave real. Con Shield nunca la tienen.»

Sin comandos: es la lámina de apertura del video.

### 0:20 – 0:35 · Conectar cualquier app en 2 líneas

```bash
cat examples/any-app/*.py 2>/dev/null || ls examples/any-app/
uv run python scripts/smoke.py --replay   # en vivo: uv run python scripts/smoke.py
```

Muestra el diff: cambiar `base_url` al gateway y usar el token
`shd_<agente>_…`. El humo marca `needs_credits` sin fallar si no hay tarjeta.

### 0:35 – 0:55 · La cuadrilla trabaja (cliente cero)

```bash
uv run python evals/run_invoices.py   # Compras: 20/20 en replay
uv run python evals/run_stock.py      # Bodega: SAM cuenta 3, voz y diferencia ok
```

Di: «Compras lee la factura con Spark visión y Bodega cuenta con SAM 3.1,
cada uno con su propio token Shield.» Aclara lo honesto: en replay las
salidas SAM son sintéticas con la gramática oficial; las tomas reales se
repiten con créditos antes del video.

### 0:55 – 1:20 · Factura envenenada: Shield la bloquea

```bash
uv run python evals/run_heldout.py
```

Muestra la tabla: la síntesis compartida da 100 % pero la held-out, ciega
a las reglas, bloquea 1/12, escala 9/12 al dueño y deja pasar 2 lecturas
que piden la credencial. «Por eso el clasificador Spark Open existe, y por
eso reportamos las dos cifras por separado.» Ninguna escritura sensible
pasa en silencio.

### 1:20 – 2:15 · Aviso real, país nuevo y rotación (401 al atacante)

```bash
uv run pytest tests/test_actions_h6.py tests/test_exposure_anomaly.py -q
```

Es el E2E en replay: anomalía (país nuevo) en Bodega → plan → aprobación
del dueño por WhatsApp/voz «sí, rota» (canal de H8) → rotación solo de
Bodega → el atacante con el token robado recibe **401** mientras Bodega,
con el token nuevo que el SDK refresca solo, sigue contando en 200.
Punta a punta <10 s frente a las ~16 h reales.

Si el gateway está desplegado (ver abajo), la misma escena contra la URL
de Cloud Run: el token revocado responde 401 y `/health` sigue ok.

```bash
curl -s https://<url-del-gateway>/health
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  https://<url-del-gateway>/v1/chat/completions \
  -H "Authorization: Bearer shd_bodega_token-robado-de-prueba" \
  -H "Content-Type: application/json" \
  -d '{"model":"muse-spark-1.3","messages":[{"role":"user","content":"hola"}]}'
# esperado: 401
```

### 2:15 – 2:35 · Cierre regulatorio y cero secretos fuera

```bash
uv run python evals/run_open_classifier.py
grep -c "BORRADOR" -r shield/notice.py 2>/dev/null || true
```

Di: «El guardián deja el borrador RGPD/LOPDP marcado BORRADOR — lo revisa
un humano — y el gate reporta 0 secretos fuera: canarios bloqueados y
llaves redactadas antes de reenviar.» Sin llave de Baseten esta eval marca
`needs_credits` y el brazo combinado coincide con el determinista: dilo
así, sin inventar la cifra en vivo.

### 2:35 – 3:00 · Métricas y qué se construyó aquí

```bash
uv run python evals/run_all.py && head -n 30 evals/report.md
```

Cierra con la tabla H2–H9 del reporte y la línea del README: todo el
código se construyó durante el hackathon (26-oct → 4-nov); lo preexistente
es solo el conocimiento del negocio y las cuentas.

## Despliegue (solo si se quiere mostrar la URL viva)

```bash
bash deploy/cloudrun.sh   # solo proyecto bendrix-hackathon, us-central1
```

Deja la URL en `ESTADO.md`. Sin créditos, el gateway responde pero el
upstream marca `needs_credits`: la demo completa sigue en replay local.
