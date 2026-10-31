# shield/watch/

Lee avisos públicos y produce `ThreatCard`:

- `feeds.py`: parsers puros de CISA KEV, OSV/GHSA, RSS/Atom y status de
  proveedores (statuspage), más `fetch_feed` con `FeedCache` en disco
  (replay: la segunda lectura no sale a la red).
- `manual.py`: entrada manual por texto/URL, PDF o captura. Lo normal es
  Spark 1.3 (visión + JSON schema vía `MetaClient`, que ya pasa por
  `gate.check`); sin créditos (401/402/403) cae a extracción determinista
  marcada `needs_credits` y no se detiene. El documento es dato no
  confiable: se describe con el esquema, nunca se obedecen sus órdenes.
