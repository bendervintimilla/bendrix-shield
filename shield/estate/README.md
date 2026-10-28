# shield/estate/

Inventario de solo lectura de las apps conectadas (H5). Cada conector
expone `list_assets() -> list[Asset]`, es inyectable para tests y ninguno
guarda valores de secretos:

- `GatewayRegistryConnector`: agentes, tokens y modelos del Registry del
  gateway (solo ids y metadatos; jamás el token en claro).
- `RailwayConnector`: solo nombres de variables por servicio (sandbox);
  si la fuente trae valores, se descartan en el conector.
- `GcpApiKeysConnector`: llaves de GCP del proyecto `bendrix-hackathon`
  (rechaza cualquier otro proyecto) con restricciones y uso, sin valores.
- `GithubSbomConnector`: SBOM desde lockfiles (`package-lock.json`,
  `requirements.txt`, `uv.lock`) sin salir a la red.
- `WebAllowlistConnector`: versión de PHP/CMS solo por header o meta y
  solo de dominios en la allowlist (SPEC §2.2); el resto se rechaza antes
  de pedir nada. Sin exploits ni escaneos.
