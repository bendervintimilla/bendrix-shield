# shield/actions/

Runbooks idempotentes y reversibles (H6): cada uno expone `plan()`, `apply()`, `verify()` y `rollback()`.

- `rotate_token(agent)`: token nuevo al instante y sin redeploy; gracia de N s para el viejo y luego `revoke`. Solo toca a ese agente.
- `rotate_upstream_key(provider)`: solo sandbox. Si el proveedor no tiene API para crear llaves, pide el paso manual (`manual_value`) y lo verifica por huella. Nunca loguea el valor.
- `redeploy(service)`: solo sandbox, vía deployer inyectado.
- `verify`: health check por agente (token activo o `health_checker` inyectado).
- `revoke`: revocación inmediata de los tokens activos de un agente.
- `patch_plan`: plan de parcheo del sandbox con su rollback.

Todo lo que tiene efecto exige `approval_id` aprobado en el `PendingRegistry` de H4/H8. La única excepción es la contención automática opcional (`Actions(auto_contain=True)` ante `reason="canary_detected"`), que queda en `Actions.audit_log` con `auto_contained=True`.

Al rotar, el token nuevo se escribe en el registro local del agente (`shield.sdk.token_store.LocalTokenStore`); el SDK lo recoge solo ante un 401 (ver `shield/sdk/`), así la cuadrilla sigue trabajando sin redeploy.

Prueba E2E en replay: `tests/test_actions_h6.py` (anomalía en Bodega → plan → aprobación simulada → rotación → atacante 401, con Compras y Bodega en 200).
