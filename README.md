# MuseShield — Business Protection

**Your app never holds the real key. One leaked token, revoked in seconds.**
MuseShield is the safety layer for AI agents and apps: in our blind
held-out v2 eval, 0/12 sensitive writes slipped through silently, and a
stolen token went from `200` to `401` in under 10 seconds (replay) —
versus ~16 hours in the real Black October incident. Shield sits between your app
and its model and tool calls, so the app never holds the real provider
key. In Black October (21 Oct 2026) AI keys were the loot: a trojanized
LiteLLM, exposed hosting variables, and our Gemini keys abused for
~16 hours (USD 310). With Shield, the loot from the same leak is one
revocable token, for one agent, with least-privilege scopes — and the
fix takes seconds, not a redeploy.

Live demo panel (replay, no secrets):
<https://bendrix-shield-panel-290240328973.us-central1.run.app>
Live gateway: <https://bendrix-shield-gateway-290240328973.us-central1.run.app>
(`/health` answers; model calls without a Shield token answer `401`).

## Connect any app in 2 lines

```python
from openai import OpenAI
import bendrix_shield as shield

client = shield.wrap(OpenAI(), "shd_<agent>_replace-with-your-token")
```

That is the whole integration: `wrap` points your OpenAI-compatible
client at the Shield gateway with your per-agent Shield token. The real
provider key stays in the gateway's vault. Tools go through the policy
with `@shield.tool(effect="read" | "write")`, and external documents are
marked as data, never instructions, with `shield.untrusted(doc)`. A
curl and a 10-line TypeScript version live in `examples/any-app/`.

If a token is rotated, a client built with a token store refreshes
itself once after a `401` and keeps working. **Threat model, in one
line:** the refresh assumes the thief stole the token from an
environment variable, a log line or a copied config value — *not* the
local token store on the agent's host. Whoever holds only the env var
cannot follow a rotation (they keep getting `401`); whoever steals the
store itself has compromised that host, and the answer is revoke +
re-issue on a clean host, not rotation alone. On Cloud Run the refresh
can also be bound to the workload's service-account identity
(`SHIELD_EXPECTED_SERVICE_ACCOUNT`, fail-closed; tested in
`tests/test_h10_hardening.py`). Full table in `docs/THREAT_MODEL.md`.

## Quickstart (5 minutes, no credits needed)

```bash
git clone https://github.com/bendervintimilla/bendrix-shield.git
cd bendrix-shield
uv sync --extra dev        # Python 3.12+ and uv
make test                  # offline suite, all green
make demo                  # gateway + panel in replay; runs docs/DEMO.md end to end
```

That is the whole first run: the demo, the attacker terminal
(`200 → 401`) and every metric in `evals/report.md` reproduce offline.
With Meta credits, add your key as `META_MODEL_API_KEY` (keychain or
Secret Manager, never committed) and run `make smoke` for one live call
per model. Deploy the gateway with `bash deploy/cloudrun.sh` (GCP
project `bendrix-hackathon` only).

## Run it live with your own key

```bash
export SHIELD_VAULT_BACKEND=env
export META_MODEL_API_KEY=<your key>   # never committed
uv sync --extra dev
make live                              # DEMO=live, panel on 127.0.0.1:8001
```

Open `/live` in your browser (the replay panel stays on `/`). Live steps
call the real Meta API through the Shield gateway and cost real credits:
see the cost shown on screen.

## Architecture

```text
                    shd_<agent>_…                 real key (vault only)
  any app ──────────────────────▶  Shield gateway  ──────────────────▶ Meta Model API
                                      │  │
                       gate.check() ──┘  └── policy.check() on every tool call
                                      │
              watch · estate · exposure · anomaly  ──▶  guardian agent
                                      │
                          owner approves on WhatsApp / voice / panel
                                      │
                    attacker with the stolen token ──▶ 401   crew keeps counting
```

- `shield/gateway/` — OpenAI-compatible proxy (`/v1/chat/completions`,
  `/v1/responses`, `/v1/audio/transcriptions`) with streaming. Maps a
  Shield token to agent, model allowlist, spend cap and the real key
  from the vault; logs agent, model, tokens, cost, latency, origin
  country and policy decision per call.
- `shield/vault/` — the real provider keys: GCP Secret Manager in the
  cloud, macOS keychain locally, memory in tests. Values are never
  logged; only name, fingerprint (sha256[:8]) and last 4 ever appear.
- `shield/gate/` — output filter: deterministic redaction of keys and
  PII, canaries, and the Muse Spark Open classifier (open weights).
- `shield/policy/` — `check(agent, tool, args, sources)` returning
  `allow | block | ask_owner`. YAML rules first (tools, sensitive fields
  by meaning — IBAN, account, key, payment domain, including aliases —
  and spend limits); Muse Spark only for the ambiguous remainder.
  External content is data: an instruction hidden in an invoice,
  including a *read* that asks to reveal a credential, key or token,
  ends in `block` or `ask_owner`, never in silence.
- `shield/sdk/` — `bendrix_shield`: the 2-line `wrap`, `@shield.tool`,
  `shield.untrusted`, and the self-healing token refresh.
- `shield/watch/`, `shield/estate/`, `shield/exposure.py`,
  `shield/anomaly.py` — public advisories to `ThreatCard`s; a read-only
  inventory of connected apps; `ThreatCard × Asset → Exposure` (sibling
  advisories with the same product and range count once); and usage
  anomalies (new country, unused model, cost spikes).
- `shield/actions/`, `shield/agent.py` — idempotent, reversible
  runbooks (`rotate_token`, `revoke`, `redeploy`, `verify`,
  `patch_plan`) and the guardian agent that orchestrates them. Every
  effect needs the owner's `approval_id`.
- `channels/`, `web/` — WhatsApp and voice approvals, plus the owner's
  panel (apps, live decisions, incidents, attacker terminal
  `200 → 401`).
- `crew/` — customer zero: Purchasing (Spark vision invoices) and
  Warehouse (SAM 3.1 counting + voice), each with its own Shield token.
- `sandbox/`, `evals/` — the Cantina Demo with test keys and an
  attacker that only ever uses our own stolen test token, and the
  evaluation sets below.

Shared schemas are in `shield/schemas.py`; the component contract is in
`docs/ARCHITECTURE.md`.

## Run the demo

Replay (no network, no credits — this is what `make demo` does):

```bash
uv sync --extra dev
make test                 # offline test suite
make demo                 # gateway + panel locally in replay; runs docs/DEMO.md end to end
uv run python evals/run_all.py   # regenerate evals/report.md
```

Live (with credits): put the Meta key in the keychain or Secret Manager
as `META_MODEL_API_KEY` (never printed, never committed), optionally add
`baseten-api-key` for Spark Open, then run `make smoke` for one minimal
call per model and `bash deploy/cloudrun.sh` for the gateway. Without a
card every live call reports `needs_credits` and nothing fails: the
whole demo still runs in replay. The full 3-minute script, beat by
beat, is `docs/DEMO.md`.

## Metrics (real, from `evals/report.md` — not inflated)

Numbers below come from `evals/report.md`. Offline rows are
replay/fixtures; rows marked **live** used real Meta models (29 Oct
2026, cost in the row). The headline injection number is held-out v2:
a fresh set written by a separate session without reading the policy
rules, frozen before measuring, never used to tune the rules. The
older held-out set is kept as history because rules were adjusted
with it in H10.

| Measurement | Result |
|---|---|
| Synthetic injection set (shares patterns with the rules; regression only) | Blocked 30/30 (100%); clean false positives 0/30 |
| **Held-out v2 (headline)** — fresh, blind to the rules, frozen | Blocked 4/12, escalated to owner 7/12, **silently allowed 1/12** — one English read asking to reveal the gateway token; sensitive writes silently allowed **0/12**. Legitimate formal account changes reach `ask_owner` 3/3; clean reads allowed 5/5 |
| **Live** held-out v2 with Muse Spark reviewing every document, stricter decision wins (2 runs, same frozen set) | Blocked 10/12 and 11/12, escalated 1 and 0, **silently allowed 1/12 in both** (same English read); legitimate changes  3/3, clean reads 5/5, false blocks 0. USD 0.1121 and 0.1316. A measurement: the shipped engine does not call Spark on every document, and on this set it made 0 Spark calls |
| Held-out v1 (history; rules were later adjusted with it) | Blocked 3/12, escalated to owner 9/12, silently allowed 0/12 after the H10 fix (2 before). Legitimate formal changes `ask_owner` 4/4; clean reads 4/4 |
| **Live** smoke: Spark 1.3, Wonder, Voice, SAM 3.1 | 4/4 `[ok]` live, USD 0.0063 |
| **Live** invoices ×20 (Spark 1.3 vision on rendered invoices) | Supplier/number/date/currency/subtotal/tax/total and arithmetic validation 20/20, USD 0.1812 |
| **Live** warehouse (SAM 3.1 synthetic images + Voice dictation) | Exact counts 4/4 with the precise prompt (`red rectangle`); with `red box` SAM returned 0 on the same images (1/4) — prompt wording matters and both are reported. Voice dictation parsed OK. USD 0.0100. No real warehouse footage yet |
| Exposure, confirmed (confidence ≥ 0.8) | Precision 1.000, recall 0.692 (TP 9, FP 0, FN 4). Before grouping sibling advisories: precision 0.643 (the twin PHP CVEs counted double). The 4 misses are Brotli, whose advisory has no parseable range: kept as candidates for Wonder triage, not invented as confirmed |
| Exposure, including candidates | Precision 0.765, recall 1.000 (TP 13, FP 4, FN 0) |
| Usage anomalies (synthetic 16 h abuse) | Precision 1.000, recall 1.000 (TP 32, FP 0, FN 0); 0 false positives on the normal series |
| Gateway overhead (local, instant fake upstream, 80 calls) | p50 1.74 ms, p95 2.48 ms (this run; see `evals/report.md`) |
| Invoices (20 synthetic, replay parser) | Total/number/arithmetic 20/20 |
| Warehouse (replay: synthetic SAM/voice outputs — no real footage yet) | Image count 3/3, video 3 unique track IDs, dictation and stock diff OK |
| Token rotation E2E (replay) | Attacker `200 → 401` in under 10 s, other agents unaffected, vs ~16 h in the real incident |
| Spark Open gate (live) | `needs_credits`: no Baseten key in the vault yet, so the live classifier number is pending, not estimated |

## Meta models used

| Model | Used for |
|---|---|
| `muse-spark-1.3` | Guardian and crew reasoning, tool calling, invoice vision, ambiguous policy calls, advisory intake |
| `muse-wonder-1.0` | Hard triage only: ambiguous exposures and difficult cases |
| Muse Spark Open (`meta-models/muse-spark-open-1026`, Baseten, Modal fallback) | Output gate classifier — the open-weights bonus path |
| `sam-3.1` | Warehouse counting (images and video track IDs) via `/v1/responses` |
| `muse-voice-transcribe-1.0` | Voice approvals ("yes, rotate it") and warehouse dictation |

Routes and prices were verified against the official docs; see
`docs/MODELS.md`. No `*-contributor` models are used.

## Built during the hackathon (26 Oct → 4 Nov 2026)

| Pre-existing (not judged) | Built during the hackathon |
|---|---|
| No code at all | Everything in this repository |
| Business knowledge: how Purchasing and Warehouse actually work | Gateway, vault, gate, policy and SDK (PRs #1, #3, #4) |
| Existing accounts (Meta, GCP `bendrix-hackathon`, GitHub) | Sandbox and evaluation sets (PR #2), lint cleanup (PR #5) |
| The Black October incident itself (the motivation) | Guardian: watch, estate, exposure, anomaly (PR #8) |
| | Containment runbooks and self-healing SDK (PR #6) |
| | Crew, customer zero (PR #7); WhatsApp/voice channels and panel (PR #9) |
| | Spark Open gate, held-out eval, Cloud Run gateway (PR #10) |
| | Final integration: public panel, held-out and exposure fixes, threat model, this README, `make demo` (PR #11, H10) |
| | Live round with real models (invoices, SAM, Voice), held-out v2, public-repo hardening (H11) |

## Name and affiliation

Built on Meta's Muse models; independent project, not affiliated with
or endorsed by Meta. «Muse» is a trademark of Meta; the MuseShield name
is a hackathon project name chosen by the team (Bendrix) and implies no
endorsement. Brand assets live in `docs/brand/`. The GitHub repository,
Python package (`bendrix_shield`) and live Cloud Run URLs keep their
original technical names — only the public product name changed.

## License

MIT — see `LICENSE`.
