# shield/gate/

Filtro de salida: `check()` bloquea canarios (con alerta), redacta de forma
determinista llaves (`sk-`, `AIza`, `LLM_`, `ghp_`, JWT, AWS, IBAN…) y PII
(correos, teléfonos) y clasifica con `classify(text)`.. Lo conecta a Muse Spark Open en Baseten (`open_classifier.py`, llave
`baseten-api-key` en el vault, Modal de respaldo): con confianza >= 0,8
bloquea secretos e inyección; sin créditos marca `needs_credits` y no
bloquea. Ver `docs/OPEN_WEIGHTS.md`.
