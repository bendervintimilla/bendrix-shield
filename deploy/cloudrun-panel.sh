#!/usr/bin/env bash
# Despliega la demo pública (replay) de Shield en el proyecto GCP de $GCP_PROJECT.
# Servicio bendrix-shield-panel: DEMO=replay, público y sin inicio de sesión,
# 1 instancia siempre encendida (abre al instante) y máximo 1 (las corridas por
# visitante viven en memoria de esa instancia), SIN secretos (no --set-secrets).
# `/` abre la pantalla nueva (esfera) corriendo la repetición grabada, una corrida por
# visitante (SHIELD_REPLAY_HOME=1; endpoints /replay/*). El modo en vivo (/live) queda apagado: cuesta dinero y exige DEMO=live.
# Uso: GCP_PROJECT=<tu-proyecto> bash deploy/cloudrun-panel.sh
set -euo pipefail

PROJECT="${GCP_PROJECT:?set GCP_PROJECT to your GCP project}"
REGION="${GCP_REGION:-us-central1}"
SERVICE="bendrix-shield-panel"

if [[ "$(gcloud config get-value project 2>/dev/null)" != "$PROJECT" ]]; then
  gcloud config set project "$PROJECT"
fi

# NO_TRAFFIC_TAG=<tag>: publica la revisión SIN tráfico y con esa etiqueta (URL de prueba
# https://<tag>---<servicio>-...run.app); se pasa al 100 % con
#   gcloud run services update-traffic "$SERVICE" --to-latest ...
# WITNESS_SRC=<carpeta>: copia SOLO cuadros redactados/verificados vacíos y sus JSON a
# deploy/witness (ignorada por git) para que la demo pública muestre las cámaras.
if [[ -n "${WITNESS_SRC:-}" ]]; then
  find deploy/witness -mindepth 1 ! -name README.md -delete
  cp "$WITNESS_SRC"/*.redacted.jpg "$WITNESS_SRC"/*.verified-empty.jpg deploy/witness/
  cp "$WITNESS_SRC"/observations.json "$WITNESS_SRC"/surveillance.json "$WITNESS_SRC"/verified-empty.json deploy/witness/
fi

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
  --concurrency=80 \
  --cpu-boost \
  --session-affinity \
  --ingress=all \
  --allow-unauthenticated \
  ${EXTRA[@]+"${EXTRA[@]}"} \
  --set-env-vars="SHIELD_SERVICE=panel,DEMO=replay,SHIELD_PANEL_SESSIONS=1,SHIELD_REPLAY_HOME=1,SHIELD_GCP_PROJECT=$PROJECT"

gcloud run services describe "$SERVICE" \
  --project="$PROJECT" --region="$REGION" --format='value(status.url)'
