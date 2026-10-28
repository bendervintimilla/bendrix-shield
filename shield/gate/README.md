# shield/gate/

Filtro de salida: `check()` bloquea canarios (con alerta), redacta de forma
determinista llaves (`sk-`, `AIza`, `LLM_`, `ghp_`, JWT, AWS, IBAN…) y PII
(correos, teléfonos) y clasifica con `classify(text)`. El clasificador es un
stub honesto en H3 (`unclassified`, nunca bloquea); H9 lo conecta a Muse
Spark Open sin cambiar la firma.
