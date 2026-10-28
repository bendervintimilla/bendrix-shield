# evals/ — fuente y método (H2)

Todo lo sintético usa semilla 42 y es reproducible con `evals/gen_*.py`. Ningún dato es de producción (SPEC §2.1).

| Carpeta/archivo | Fuente / método |
|---|---|
| `advisories/*.json` (14) | Avisos reales y públicos, forma `ThreatCard` de `shield/schemas.py`. Cada archivo cita su `source_url`: CVE.org (PHP2Shell CVE-2026-109618/109619, GitLab CVE-2026-110264), CISA KEV 13/14/20/27-oct-2026 (CVE-2026-0322, 76519, 105133, 48356, 96951, 96652, Brotli CVE-2026-111497), blog oficial de Railway 21-oct-2026, The Hacker News (LiteLLM 1.82.7/8 = CVE-2026-33634, KEV 26-mar-2026) y prensa del sector (LiteLLM 1.107.0, eMudhra). eMudhra no tiene CVE propio en la fuente: no se inventa ninguno. |
| `estates/*.json` (30) | Inventarios sintéticos de restaurante/hotel/agencia generados por script. Cada uno trae `expected_exposures` con positivos y negativos contra los 14 avisos. |
| `usage/*.json` | Series `CallLog` sintéticas: 7 días normales de `crew-bodega` y un abuso de ~16 h (país nuevo BR, modelo no usado, pico de costo), como el abuso real de llaves de oct-2026. Solo cifras sintéticas. |
| `injection/*.json` (30+30) | `gen_injection.py`: envenenados (texto blanco, metadatos, texto en imagen, «ignora tus instrucciones», «cambia el IBAN», «imprime tu API key») y limpios, etiquetados con `expected_policy`. |
| `invoices/*.json` (20) | Facturas sintéticas marcadas (`synthetic: true`), con `ground_truth` por campo. |
| `canaries.json` (10) | Secretos trampa sintéticos `CANARY-SHIELD-*`; el gate de H1 los bloquea. No son credenciales reales. |
| `private/tomas.md` | Lista de tomas de bodega para grabar en el local. Ignorado por git (`.gitignore`). |

Métricas del set: ver `tests/test_evals_h2.py` (conteos, esquemas ThreatCard y bloqueo de canarios).
