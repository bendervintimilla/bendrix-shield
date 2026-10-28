#!/usr/bin/env bash
# Despliega el gateway de Shield SOLO en el proyecto bendrix-hackathon.
# Región us-central1, min 0 / max 2 instancias. Los secretos se montan
# desde Secret Manager (--set-secrets); ninguno va en la imagen ni en git.
# Uso: bash deploy/cloudrun.sh
set -euo pipefail

PROJECT="bendrix-hackathon"
REGION="us-central1"
SERVICE="bendrix-shield-gateway"

if [[ "$(gcloud config get-value project 2>/dev/null)" != "$PROJECT" ]]; then
  gcloud config set project "$PROJECT"
fi

SECRETS="META_MODEL_API_KEY=hackathon-meta-model-api-key:latest"
if gcloud secrets describe baseten-api-key --project="$PROJECT" >/dev/null 2>&1; then
  SECRETS="$SECRETS,BASETEN_API_KEY=baseten-api-key:latest"
else
  echo "Aviso: el secreto baseten-api-key aún no existe en Secret Manager;"
  echo "Spark Open quedará en needs_credits hasta crearlo (ver docs/OPEN_WEIGHTS.md)."
fi

gcloud run deploy "$SERVICE" \
  --project="$PROJECT" \
  --region="$REGION" \
  --source=. \
  --min-instances=0 \
  --max-instances=2 \
  --allow-unauthenticated \
  --set-env-vars="SHIELD_VAULT_BACKEND=env,SHIELD_REPLAY=0" \
  --set-secrets="$SECRETS"

gcloud run services describe "$SERVICE" \
  --project="$PROJECT" --region="$REGION" --format='value(status.url)'
