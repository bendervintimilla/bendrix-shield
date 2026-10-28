# crew/compras/

Agente de Compras (H7): ledger SQLite (insumos, proveedores con su cuenta
de pago, compras idempotentes por hash, costo promedio ponderado y
recetas de 1 nivel), `extract_invoice` con Spark 1.3 en visión y
validación aritmética con tolerancia 0,02. Herramientas vía
`@shield.tool`: `propose_purchase` y `recost_dish` (read),
`post_purchase` (write, idempotente) y `update_supplier_account`
(write, sensible). La factura envenenada («cambia el IBAN») termina en
`block` con evidencia; ver `crew/orchestrator.py`.
