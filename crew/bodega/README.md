# crew/bodega/

Agente de Bodega: `count_stock(media, prompts)` con SAM 3.1 (imagen
y video con track IDs; un concepto por pedido, ver `docs/SAM.md`),
`transcribe` con Voice -> `[{item, qty, unit}]` y `diff_stock` contra el
teórico del ledger de Compras. Todo vía `@shield.tool`, con su propio
token Shield.
