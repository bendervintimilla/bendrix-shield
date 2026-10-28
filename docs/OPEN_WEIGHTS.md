# Spark Open en Baseten (bono Open Weights) — H9

Clasificador de secretos e inyección del gate con **Muse Spark Open**
(`spark-open`), servido por un socio de inferencia porque los pesos abiertos
no corren en la Meta Model API. Código: `shield/gate/open_classifier.py`.

## Proveedor primario: Baseten

Verificado el 28-oct-2026 en el anuncio oficial de Baseten «Muse Spark Open
and Nemotron 3.5 Super VL available on Baseten» (15-oct-2026): el modelo se
sirve por las Model APIs con el endpoint compatible con OpenAI:

```bash
curl https://inference.baseten.co/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $BASETEN_API_KEY" \
  -d '{
    "model": "meta-models/muse-spark-open-1026",
    "messages": [{"role": "user", "content": "…"}]
  }'
```

El anuncio publica el slug `meta-models/muse-spark-open`; el SPEC de Shield
fija `meta-models/muse-spark-open-1026` y ese es el default del código. Si
la consola de Baseten muestra otro slug, se cambia sin tocar código con
`SHIELD_SPARK_OPEN_MODEL`. El clasificador pide `response_format` con JSON
schema (`label` en `clean|secret|injection`, `score`, `reason`) y solo
bloquea con confianza ≥ 0,8.

### Llave en el vault

```bash
# Local (llavero de macOS, backend por defecto):
security add-generic-password -U -s baseten-api-key -a hackathon -w '<la-llave>'

# Nube (Secret Manager en bendrix-hackathon; Cloud Run la monta como env):
printf '%s' '<la-llave>' | gcloud secrets create baseten-api-key \
  --project=bendrix-hackathon --data-file=-
```

El código lee `baseten-api-key` del vault (o `BASETEN_API_KEY` del entorno
en CI/Cloud Run). El valor nunca se loguea: fuera del header solo viajan el
nombre, la huella sha256[:8] y los últimos 4 (interfaz del vault de H3).

### Activación

```python
from shield.gate import make_open_classifier, set_classifier

set_classifier(make_open_classifier())  # Baseten por defecto
```

Sin llave o con 401/402/403 el clasificador devuelve `needs_credits` y no
bloquea: mandan la redacción determinista y los canarios. Con
`SHIELD_REPLAY=1` responde solo desde la caché por hash de
`SHIELD_REPLAY_DIR` (las llamadas en vivo guardan su respuesta ahí).

## Respaldo: Modal

Mismo modelo y misma forma Chat Completions; el operador despliega el
endpoint en Modal y configura:

```bash
export SHIELD_SPARK_OPEN_PROVIDER=modal          # o solo el respaldo:
export SHIELD_SPARK_OPEN_FALLBACK=modal          # si Baseten da 401/402/403
export SHIELD_SPARK_OPEN_MODAL_URL=https://<tu-endpoint>/v1
# llave: 'modal-api-key' en el vault o MODAL_API_KEY en el entorno
```

## Estado al 28-oct-2026

No hay llave de Baseten en el vault ni créditos aprobados: el despliegue
queda documentado y probado con replay/transporte falso
(`tests/test_open_classifier_h9.py`), y la comparación contra la redacción
determinista sola corre en modo `needs_credits` (ver `evals/report.md`,
sección «Gate Spark Open vs determinista solo»). Con la llave creada, la
misma eval mide el aporte real en los secretos ofuscados.
