# Architecture — NoKey

Shield es la capa de seguridad para agentes y apps de IA de la pyme. Cualquier
app se conecta en 2 líneas y Shield se pone en medio de sus llamadas a modelos
y de sus herramientas. Las apps nunca tienen la llave real del proveedor: solo
un token de Shield revocable al instante, por agente y con permisos mínimos.

## Flujo

```text
app ──(token Shield shd_<agente>_…)──▶ gateway ──(llave real, vault)──▶ Meta Model API
                                          │
                          gate.check(salida) · policy.check(herramienta)
                                          │
                                     watch · estate · exposure · anomaly
                                          │
                                     agente guardián ──▶ actions (con OK del dueño)
                                          │
                                     WhatsApp / voz / panel
```

## Componentes (SPEC §1)

| Carpeta | Qué hace | Sesión |
|---|---|---|
| `shield/gateway/` | Proxy compatible con OpenAI con streaming; mapea token → agente → llave del vault; registra cada llamada | H3 |
| `shield/vault/` | Llaves reales (Secret Manager / llavero / env en tests); nunca se loguea el valor | H3 |
| `shield/gate/` | Filtro de salida: redacción, canarios y clasificador Spark Open | H1 stub, H3 completo |
| `shield/policy/` | `check(agent, tool, args, sources) -> PolicyDecision`; reglas YAML primero, Spark para lo ambiguo | H4 |
| `shield/sdk/` | `shield.wrap(client)`, `@shield.tool(...)`, `shield.untrusted(doc)` | H3/H4 |
| `shield/watch/` | Avisos públicos → `ThreatCard` | H5 |
| `shield/estate/` | Inventario de solo lectura de apps conectadas | H5 |
| `shield/exposure.py` | `ThreatCard × Asset → Exposure` | H5 |
| `shield/anomaly.py` | Uso raro por agente o llave (estadística) | H5 |
| `shield/actions/` | Runbooks idempotentes y reversibles; todo efecto pide OK del dueño | H6 |
| `shield/agent.py` | El agente guardián (tool calling) | H5 |
| `channels/` | WhatsApp + aprobación por voz | H8 |
| `web/` | Panel FastAPI + HTMX | H8 |
| `crew/` | Cliente cero: Compras + Bodega vía SDK y gateway | H7 |
| `sandbox/` | Cantina Demo y atacante con llaves de prueba propias | H2/H6 |
| `evals/` | Avisos, estates, uso, inyecciones, facturas y canarios | H2 |

## Esquemas mínimos (SPEC §3)

Definidos como modelos Pydantic en `shield/schemas.py`. Son el contrato entre
sesiones: si necesitas cambiar un campo, anótalo en tu PR.

| Esquema | Campos |
|---|---|
| `ThreatCard` | `id, source_url, published_at, products[{name, ecosystem, affected_versions, fixed_versions}], iocs[], actions[], severity` |
| `Asset` | `id, kind, name, owner_app, platform, fingerprint, last4, metadata` |
| `Exposure` | `threat_id, asset_id, reason, confidence` (0..1) |
| `AgentToken` | `token_id, agent, app, scopes[], models[], spend_cap_usd, status` (`active`/`revoked`/`rotated`) |
| `CallLog` | `ts, agent, model, tokens_in, tokens_out, cost_usd, latency_ms, src_ip, src_country, decision` |
| `ToolCall` | `agent, tool, args_redacted, source_doc_ids[]` |
| `PolicyDecision` | `decision` (`allow`/`block`/`ask_owner`), `reason, evidence[]` |

## Invariantes que el código debe respetar

1. Cero producción: solo el proyecto GCP `bendrix-hackathon` y el sandbox.
2. Defensa pura: el atacante usa llaves de prueba propias, solo contra el gateway propio.
3. La llave de Meta es `META_MODEL_API_KEY` (llavero o Secret Manager); nunca se imprime ni se commitea.
4. Todo payload saliente pasa por `gate.check` y toda herramienta con efecto pasa por `policy.check`.
5. Un agente = un token = un alcance. Rotar uno no tumba a los demás.
6. Modo replay (respuestas guardadas por hash) para que la demo y los tests corran sin red ni créditos.
7. Nada de modelos `*-contributor` en el código del repo.

## Spark review per document (policy)

`PolicyEngine(spark_review=True)` adds one Muse Spark 1.3 review per
untrusted document, cached by text hash inside the engine instance, and
keeps the strictest decision (`block` > `ask_owner` > `allow`) between
the deterministic rules and Spark — the same combination as arm B of
`evals/run_heldout2_spark.py`. A deterministic `block` skips Spark. If
Spark fails or has no credits, the deterministic decision is kept and
`spark_unavailable` is added to the evidence: a failure never relaxes
anything and never blocks on its own. It is off by default, enabled
with `SHIELD_SPARK_REVIEW=on` in the crew and the live chain only when
real credentials are present; replay and tests run without it.

Measured on 2026-10-31 (`evals/recorded/spark-latency-2026-10-31.json`
and `evals/recorded/heldout2-spark-run*.json`): USD 0.0061 per document,
5.3 s p50 and 10.2 s p90 per call. Arm B blocked 10–11 of 12 poisoned
documents versus 4 for the deterministic arm, with 0 false blocks.

This review never runs in the gateway hot path: 5–10 s and USD 0.0061
on every proxied model call would break gateway latency and cost.
Documents are reviewed once (then cached), off that path.

## Cliente de modelos

`shield/meta_client.py` es el único punto que habla con la Meta Model API.
Rutas, precios y límites reales están en `docs/MODELS.md`.
