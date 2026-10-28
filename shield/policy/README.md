# shield/policy/

`check(agent, tool, args, sources) -> PolicyDecision` (H4).

- Reglas YAML por agente en `policies/*.yaml`: herramientas permitidas,
  `effect` (read/write), campos sensibles, `ask_owner_if` y límites.
- Orden: reglas deterministas → inyección en fuentes no confiables →
  campos sensibles/límites → Muse Spark 1.3 solo para lo ambiguo
  (JSON schema, razón corta; sin créditos escala a `ask_owner`).
- Campos sensibles por significado: cualquier alias que contenga IBAN,
  cuenta, llave, secreto, pago, dominio o correo se trata como sensible.
- `shield.untrusted(doc)` marca el contenido externo como dato. Si una
  acción con efecto se deriva de un documento con órdenes al agente o
  que pide cambiar un campo sensible, se bloquea con evidencia
  (fragmento y ubicación: `body`, `white_text`, `metadata:<clave>`,
  `image:text`, `image:vision`).
- Extracción: PDF con stdlib (cuerpo, texto blanco y metadatos) e imagen
  PNG (chunk `tEXt`; visión Spark como respaldo, falla suave sin créditos).
