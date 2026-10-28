# shield/sdk/

Paquete `bendrix_shield`: `shield.wrap(client)` (H3), `@shield.tool(...)`
y `shield.untrusted(doc)` (H4).

```python
import shield

doc = shield.untrusted(pdf_bytes, doc_id="factura-88")  # dato, no instrucción

@shield.tool(effect="write", agent="compras")
def update_supplier_bank(iban: str, _sources=None): ...

update_supplier_bank(iban="EC...", _sources=[doc])
# allow -> ejecuta · block -> PolicyBlocked · ask_owner -> PolicyPending
# con pending_id en default_registry, listo para el canal de H8:
# default_registry.approve(pending_id) ejecuta recién con el OK del dueño.
```
