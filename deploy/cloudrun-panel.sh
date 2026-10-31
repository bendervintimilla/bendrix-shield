#!/usr/bin/env bash
# Despliega el panel público de Shield en el proyecto GCP de $GCP_PROJECT.
# Servicio bendrix-shield-panel: DEMO=replay, min 0 / max 2, público,
# SIN secretos de escritura (no --set-secrets). El panel en replay usa
# su gateway en proceso; SHIELD_GATEWAY_URL apunta al gateway vivo
# para cuando se sirva en modo conectado.
# Uso: GCP_PROJECT=<tu-proyecto> GATEWAY_URL=<url-del-gateway> bash deploy/cloudrun-panel.sh
set -euo pipefail

PROJECT="${GCP_PROJECT:?set GCP_PROJECT to your GCP project}"
REGION="${GCP_REGION:-us-central1}"
SERVICE="bendrix-shield-panel"
GATEWAY_URL="${GATEWAY_URL:?set GATEWAY_URL to the deployed gateway URL}"

if [[ "$(gcloud config get-value project 2>/dev/null)" != "$PROJECT" ]]; then
  gcloud config set project "$PROJECT"
fi

gcloud run deploy "$SERVICE" \
  --project="$PROJECT" \
  --region="$REGION" \
  --source=. \
  --min-instances=0 \
  --max-instances=2 \
  --allow-unauthenticated \
  --set-env-vars="SHIELD_SERVICE=panel,DEMO=replay,SHIELD_GATEWAY_URL=$GATEWAY_URL,SHIELD_GCP_PROJECT=$PROJECT"

gcloud run services describe "$SERVICE" \
  --project="$PROJECT" --region="$REGION" --format='value(status.url)'
