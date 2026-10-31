# Guía de la demo — NoKey — Business Protection

Nombre público: «NoKey, Business Protection». Aviso de no afiliación:
*Built on Meta's Muse models; independent project, not affiliated with
or endorsed by Meta.* Portadas: `docs/brand/slides/`.

Dos modos con los mismos comandos: **replay** (sin red ni créditos) y
**en vivo** (con créditos Meta y, opcionalmente, la llave de Baseten en
el vault). En replay todo lo que necesite un modelo responde
`needs_credits` o sale de la caché por hash, y la demo no se cae.
WhatsApp es un webhook en modo simulador, sin credenciales reales; la
cadena viva usa voz.

## Antes de empezar

```bash
git clone https://github.com/bendervintimilla/bendrix-shield.git && cd bendrix-shield
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

## Recorrido

### 1. El problema

El 21-oct-2026 las llaves de IA fueron el botín (paquete troyanizado,
variables de nube expuestas, ~16 h de abuso, USD 310). Las apps tenían
la llave real; con NoKey solo tienen un token revocable por agente.

### 2. Conectar cualquier app en 2 líneas

```bash
cat examples/any-app/*.py 2>/dev/null || ls examples/any-app/
uv run python scripts/smoke.py --replay   # en vivo: uv run python scripts/smoke.py
```

La integración cambia `base_url` al gateway y usa el token
`shd_<agente>_…`. El humo marca `needs_credits` sin fallar si no hay
tarjeta.

### 3. La cuadrilla trabaja

```bash
uv run python evals/run_invoices.py   # Compras: 20/20 en replay
uv run python evals/run_stock.py      # Bodega: SAM cuenta 3 (esperado 3), voz y diferencia ok
```

Compras lee la factura con Spark visión y Bodega cuenta con SAM 3.1,
cada uno con su propio token. En replay las salidas SAM son sintéticas
con la gramática oficial.

### 4. Factura envenenada

```bash
uv run python evals/run_heldout.py
```

La sintética compartida da 100 % pero la held-out, ciega a las reglas,
es la cifra de referencia. En held-out v2 sin revisión: bloquea 4/12,
escala 7/12 al dueño y deja pasar en silencio 1/12 (una lectura en
inglés que pide revelar el token, `v2-poison-token-en`); escrituras
sensibles en silencio 0/12. Con revisión Spark por documento (3
corridas): bloquea 12, 10 y 11/12; en silencio 0, 1 y 1 (la misma
lectura en inglés en 2 de 3 corridas); falsos bloqueos 1, 0 y 0.

### 5. Aviso, país nuevo y rotación (401 al atacante)

```bash
uv run pytest tests/test_actions_h6.py tests/test_exposure_anomaly.py -q
```

Es el E2E en replay: anomalía (país nuevo) en Bodega → plan →
aprobación del dueño por voz o panel (WhatsApp es un webhook en
simulador) → rotación solo de Bodega → el atacante con el token robado
recibe **401** mientras Bodega, con el token nuevo que el SDK refresca
solo, sigue contando en 200. Punta a punta <10 s en replay frente a
las ~16 h reales.

Si el gateway está desplegado (ver abajo), la misma escena contra la
URL de Cloud Run: el token revocado responde 401 y `/health` sigue ok.

```bash
curl -s https://<url-del-gateway>/health
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  https://<url-del-gateway>/v1/chat/completions \
  -H "Authorization: Bearer shd_<agent>_..." \
  -H "Content-Type: application/json" \
  -d '{"model":"muse-spark-1.3","messages":[{"role":"user","content":"hola"}]}'
# esperado: 401
```

### 6. Cierre y cero secretos fuera

```bash
uv run python evals/run_open_classifier.py
grep -c "BORRADOR" -r shield/notice.py 2>/dev/null || true
```

El guardián deja el borrador marcado BORRADOR para revisión humana, y
el gate reporta 0 secretos fuera: canarios bloqueados y llaves
redactadas antes de reenviar. Sin llave de Baseten esta eval marca
`needs_credits` y el brazo combinado coincide con el determinista.
Spark Open no se ha corrido en vivo por falta de créditos.

### 7. Métricas

```bash
uv run python evals/run_all.py && head -n 30 evals/report.md
```

Todas las cifras están en `evals/report.md` y `evals/recorded/`.

## Despliegue (solo si se quiere mostrar la URL viva)

```bash
export GCP_PROJECT=<tu-proyecto>
bash deploy/cloudrun.sh   # proyecto de $GCP_PROJECT, us-central1
```

Sin créditos, el gateway responde pero el upstream marca
`needs_credits`: la demo completa sigue en replay local.
