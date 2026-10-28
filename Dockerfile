# Bendrix Shield — gateway (+ panel cuando H8 lo fusione) para Cloud Run.
# La llave real vive en Secret Manager y entra por --set-secrets como
# variable de entorno (SHIELD_VAULT_BACKEND=env); la imagen no trae secretos.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SHIELD_VAULT_BACKEND=env \
    SHIELD_REGISTRY_DB=/tmp/shield-registry.db

WORKDIR /app
COPY pyproject.toml README.md ./
COPY shield ./shield
COPY bendrix_shield ./bendrix_shield
COPY web ./web
COPY channels ./channels
COPY sandbox ./sandbox

RUN pip install --upgrade pip && pip install .

EXPOSE 8080
# Cloud Run inyecta $PORT (8080 por defecto). SHIELD_SERVICE=panel sirve
# el panel (web.app, DEMO=replay); sin esa variable arranca el gateway.
CMD ["sh", "-c", "if [ \"$SHIELD_SERVICE\" = \"panel\" ]; then exec uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-8080}; else exec uvicorn shield.gateway.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8080}; fi"]
