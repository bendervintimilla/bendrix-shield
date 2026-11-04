#!/usr/bin/env bash
# Despliega el modo EN VIVO protegido (modelos reales de Meta) como servicio aparte:
# bendrix-shield-live. La demo pública en replay (bendrix-shield-panel) no se toca.
#
# * Código de acceso: Secret Manager `shield-live-access-code` -> LIVE_ACCESS_CODE.
#   Para verlo:  gcloud secrets versions access latest --secret=shield-live-access-code \
#                  --project=$GCP_PROJECT
# * Llave de la Meta Model API: Secret Manager -> META_MODEL_API_KEY (nunca en la imagen).
# * Tope duro en el servidor: USD 5 y 20 corridas por día (hora de Ecuador), registro en
#   gs://$GCP_PROJECT-shield-ledger (sobrevive reinicios); USD 0.60 por corrida.
# * min=max=1 instancia: la cadena en vivo vive en memoria y el tope no se reparte.
# Uso: GCP_PROJECT=<proyecto> bash deploy/cloudrun-live.sh
set -euo pipefail

PROJECT="${GCP_PROJECT:?set GCP_PROJECT to your GCP project}"
REGION="${GCP_REGION:-us-central1}"
SERVICE="bendrix-shield-live"
KEY_SECRET="${META_KEY_SECRET:-hackathon-meta-model-api-key}"
CODE_SECRET="${LIVE_CODE_SECRET:-shield-live-access-code}"
LEDGER="gs://${PROJECT}-shield-ledger/live-ledger.json"

# NO_TRAFFIC_TAG=<tag>: publica la revisión SIN tráfico y con esa etiqueta (URL de prueba
# https://<tag>---<servicio>-...run.app); se pasa al 100 % con
#   gcloud run services update-traffic "$SERVICE" --to-latest ...
EXTRA=()
if [[ -n "${NO_TRAFFIC_TAG:-}" ]]; then
  EXTRA+=(--no-traffic "--tag=${NO_TRAFFIC_TAG}")
fi

gcloud run deploy "$SERVICE" \
  --project="$PROJECT" \
  --region="$REGION" \
  --source=. \
  --min-instances=1 \
  --max-instances=1 \
  --concurrency=20 \
  --timeout=300 \
  --cpu-boost \
  --session-affinity \
  --ingress=all \
  --allow-unauthenticated \
  ${EXTRA[@]+"${EXTRA[@]}"} \
  --set-env-vars="SHIELD_SERVICE=panel,DEMO=live,SHIELD_LIVE_REMOTE=1,SHIELD_SPARK_REVIEW=on,SHIELD_LIVE_CAP_USD=0.60,SHIELD_LIVE_DAILY_USD=5,SHIELD_LIVE_DAILY_RUNS=20,SHIELD_LEDGER_GCS=${LEDGER},SHIELD_GCP_PROJECT=$PROJECT,SHIELD_REPLAY_URL=${REPLAY_URL:-https://bendrix-shield-panel-290240328973.us-central1.run.app/}" \
  --set-secrets="META_MODEL_API_KEY=${KEY_SECRET}:latest,LIVE_ACCESS_CODE=${CODE_SECRET}:latest"

gcloud run services describe "$SERVICE" \
  --project="$PROJECT" --region="$REGION" --format='value(status.url)'
