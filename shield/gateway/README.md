# shield/gateway/

Proxy compatible con OpenAI (`/v1/chat/completions`, `/v1/responses`, `/v1/audio/transcriptions` y la ruta de SAM). Recibe un token de Shield, lo mapea a agente → proveedor → llave del vault, aplica la política y reenvía. Lo construye H3.
