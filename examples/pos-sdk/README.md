# examples/pos-sdk/

Agente de caja de un punto de venta con el SDK de Wairrior (`@shield.tool`).
Cada herramienta pasa por la política de [policies/caja.yaml](policies/caja.yaml)
antes de ejecutarse:

| Acción | Decisión | Por qué |
|---|---|---|
| `emitir_factura` | allow | herramienta permitida, monto bajo el límite |
| `anular_factura` | block | no está en la política: lo no listado se bloquea |
| `cambiar_cuenta_proveedor` | ask_owner | `cuenta_bancaria` es campo sensible; queda pendiente hasta que el dueño apruebe (`PendingRegistry.approve`) |

```bash
uv run python examples/pos-sdk/run.py   # sin red, sin llaves, datos de juguete
```

No hace llamadas reales ni usa llaves. Si el agente además habla con un
modelo, su cliente OpenAI se conecta igual que en
[examples/any-app](../any-app/): `shield.wrap(OpenAI(), "shd_…", agent="caja")`.

Prueba: `tests/test_example_pos_sdk.py`.
