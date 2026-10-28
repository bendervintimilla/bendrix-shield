#!/usr/bin/env bash
# Despliega el panel público de Shield SOLO en bendrix-hackathon.
# Servicio bendrix-shield-panel: DEMO=replay, min 0 / max 2, público,
# SIN secretos de escritura (no --set-secrets). El panel en replay usa
# su gateway en proceso; SHIELD_GATEWAY_URL apunta al gateway vivo
# para cuando se sirva en modo conectado.
# Uso: bash deploy/cloudrun-panel.sh
set -euo pipefail

PROJECT="bendrix-hackathon"
REGION="us-central1"
SERVICE="bendrix-shield-panel"
GATEWAY_URL="https://bendrix-shield-gateway-290240328973.us-central1.run.app"

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
  --set-env-vars="SHIELD_SERVICE=panel,DEMO=replay,SHIELD_GATEWAY_URL=$GATEWAY_URL"

gcloud run services describe "$SERVICE" \
  --project="$PROJECT" --region="$REGION" --format='value(status.url)'
