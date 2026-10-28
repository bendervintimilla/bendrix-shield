# examples/any-app/

Cualquier app se conecta a Shield en 2 líneas: apuntas tu cliente OpenAI al
gateway con `wrap` y usas tu token Shield (`shd_…`). La llave real del
proveedor vive solo en el vault del gateway.

- Python (10 líneas): [connect.py](connect.py)
- TypeScript (10 líneas): [connect.ts](connect.ts)
- curl: [connect.sh](connect.sh)

Arranque del gateway local:

```bash
SHIELD_VAULT_BACKEND=memory uv run python -m shield.gateway.app
# o: uv run uvicorn --factory shield.gateway.app:create_app --port 8000
```
