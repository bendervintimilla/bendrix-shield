# Bendrix Shield

**The safety layer for AI agents and apps.** Any app connects in 2 lines and
Shield sits between the app and its model and tool calls. Our crew (Purchasing
+ Warehouse) is the demo's customer zero, and a second minimal example proves
it works for any app.

## Why

In Black October (21 Oct 2026) AI keys were the loot: a trojanized LiteLLM,
exposed Railway variables, and our Gemini keys abused for ~16 hours (USD 310).
With Shield, **apps never hold the real provider key** — only an instantly
revocable Shield token, per agent, with least-privilege scopes. Rotate one
token and nobody else goes down.

## How it works

```text
                    shd_<agent>_…                 real key (vault only)
  any app ──────────────────────▶  Shield gateway  ──────────────────▶ Meta Model API
                                      │  │
                       gate.check() ──┘  └── policy.check() on every tool call
                                      │
              watch · estate · exposure · anomaly  ──▶  guardian agent
                                      │
                          owner approves on WhatsApp (voice: "yes, rotate it")
                                      │
                    attacker with the stolen token ──▶ 401   crew keeps counting
```

## Connect any app in 2 lines

```python
from openai import OpenAI
import shield  # planned SDK (H3): shield.wrap(client) — today, point base_url at the gateway

client = shield.wrap(OpenAI(base_url="https://api.meta.ai/v1", api_key="shd_<agent>_…"))
```

Until the gateway lands in H3, the same 2-line shape works against the Meta
Model API through `shield/meta_client.py`; the token swap is the only change.

## Models (Meta Model API)

| Job | Model |
|---|---|
| Agent / guardian reasoning | `muse-spark-1.3`, hard cases `muse-wonder-1.0` |
| Output classifier (open weights bonus) | Muse Spark Open (`meta-models/muse-spark-open-1026`, Baseten) |
| Warehouse counting | `sam-3.1` |
| Voice approvals | `muse-voice-transcribe-1.0` |

## Quickstart

```bash
uv sync --extra dev
make test    # offline: fake transport + replay, no credits needed
make smoke   # 1 minimal live call per model; prints needs_credits without failing if there is no card yet
```

## Pre-existing (not judged) vs Built during the hackathon (26 Oct → 4 Nov 2026)

| Pre-existing (not judged) | Built during the hackathon (26 Oct → 4 Nov 2026) |
|---|---|
| No code at all | Everything in this repository |
| Business knowledge: how Purchasing and Warehouse actually work | Gateway, vault, gate, policy, SDK, watch, estate, exposure, anomaly, actions, guardian agent |
| Existing accounts (Meta, GCP project `bendrix-hackathon`, GitHub) | Channels (WhatsApp + voice), web panel, crew (customer zero), sandbox and evals |
| The Black October incident itself (the motivation) | The 3-minute demo and its replay fixtures |

## Layout

See `docs/ARCHITECTURE.md` for the component map and the shared schemas in
`shield/schemas.py`. Routes and prices verified against the official docs are
in `docs/MODELS.md`.

## License

MIT — see `LICENSE`.
