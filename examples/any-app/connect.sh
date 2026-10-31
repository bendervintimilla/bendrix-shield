#!/bin/sh
# Cualquier app se conecta a Shield con un curl: token Shield, nunca la llave real.
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer shd_<agent>_..." \
  -H "Content-Type: application/json" \
  -d '{"model":"muse-spark-1.3","messages":[{"role":"user","content":"Reply with: connected"}]}'
