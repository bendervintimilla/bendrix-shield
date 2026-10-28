# shield/vault/

Llaves reales del proveedor con interfaz `get/put/fingerprint/last4` y tres
backends: Secret Manager (`bendrix-hackathon`), llavero de macOS y memoria
(tests). El valor nunca se loguea: solo nombre, huella sha256[:8] y últimos 4.
Backend por entorno: `SHIELD_VAULT_BACKEND=memory|keychain|secret-manager`.
