# NoKey — Business Protection

NoKey is the safety layer between SMEs' AI agents and the models and tools they call.
For SMEs running AI agents — Purchasing reads supplier invoices, Warehouse counts stock — without handing those agents the real provider key.

- **One token per agent:** each agent gets its own revocable `shd_<agent>_…` token, with least-privilege scopes and a spend cap.
- **The real key never enters the app:** it stays in the gateway vault; apps only ever see their Shield token.
- **Rotation the owner approves by voice:** nothing rotates without the owner's approval (voice, WhatsApp or panel); then the stolen token answers `401`.
- **Poisoned documents are blocked, not obeyed:** external documents are data, never instructions; they end in `block` or `ask_owner`, with per-document Muse Spark review when enabled.

**Try it**

```bash
uv sync --extra dev
make demo   # replay, no key needed
make live   # with your META_MODEL_API_KEY; see Run it live
```

| Figure | Result | Source |
|---|---|---|
| Held-out v2, rules only | Blocked 4/12, to owner 7/12, silent 1/12 (a read; sensitive writes 0/12) | `evals/report.md` H11 held-out v2 |
| Held-out v2, per-document Spark review (3 runs) | Blocked 12, 10, 11/12; silent 0, 1, 1; false blocks 1, 0, 0 | `evals/report.md` H15; `evals/recorded/heldout2-spark-armc*.json` |
| Stolen-token rotation (replay) | Attacker `200 → 401` in under 10 seconds | `tests/test_actions_h6.py`; `evals/report.md` H6 |
| Live chain recorded 2026-10-31 | USD 0.0749 in 84.7 s; stolen token `401`, crew token `200` after refresh | `evals/recorded/live-run-2026-10-31.json` |

Detail for every figure is in Metrics below. Held-out v2 is fresh, blind to the policy rules and frozen before measuring (`evals/heldout2/`).

Motivation, as already documented in this repo (`docs/DEMO.md`): in the
October 2026 incident behind this project, exposed keys were abused for
~16 hours (USD 310). With NoKey the loot from the same kind of leak is one
revocable per-agent token, and the fix is a rotation, not a redeploy.
No hosted demo is required to judge this project: `make demo` runs the
full story locally in replay, and `make live` runs it against the real
Meta API with your own key (see below).

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

That is the whole first run: the demo and the attacker terminal
(`200 → 401`) reproduce offline. The offline rows in `evals/report.md`
reproduce offline; the live rows do not reproduce without a key and are
recorded in `evals/recorded/`.
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

Open `/live` in your browser (the replay panel stays on `/`). Warning:
`make live` turns on per-document Spark review (`SHIELD_SPARK_REVIEW=on`
in the `Makefile`). Live steps call the real Meta API through the Shield
gateway and cost real credits: see the cost shown on screen.

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
| **Live** held-out v2, shipped engine with per-document Spark review (3 runs, same frozen set; H15 section) | Blocked 12, 10 and 11 of 12; to owner 0, 1 and 0; silently allowed 0, 1 and 1 (same English read, `v2-poison-token-en`); legitimate 2/3, 3/3 and 3/3 in `ask_owner`; clean reads 5/5; false blocks 1, 0 and 0 (the 1 is `v2-clean-formal-en`, run 1). USD 0.0975, 0.0913 and 0.0856; 16 Spark calls per run. Earlier arm-B measurement (Spark on every case, stricter wins; 3 runs): blocked 10, 11 and 11 of 12; to owner 1, 0 and 0; silently allowed 1 in each run (same English read); legitimate 3/3, 3/3 and 2/3 in `ask_owner`; clean reads 5/5 in each run; false blocks 0, 0 and 1 (the 1 is `v2-clean-formal-en` in the third run, recorded in `evals/recorded/heldout2-spark-armc-2026-10-31.json` arm B). USD 0.1121, 0.1316 and 0.1102; 20 Spark calls per run — see H14 and H15 sections |
| Held-out v1 (history; rules were later adjusted with it) | Blocked 3/12, escalated to owner 9/12, silently allowed 0/12 after the H10 fix (2 before). Legitimate formal changes `ask_owner` 4/4; clean reads 4/4 |
| **Live** chain through the gateway, recorded 2026-10-31 (`evals/recorded/live-run-2026-10-31.json`) | Invoice vision, SAM 3.1 count, stolen-token attack, guardian, voice transcription and approved rotation in one run; stolen token `401` after rotation, crew `200` after refresh; USD 0.0749, 84.7 s. Warehouse image is AI-generated test material, not real footage |
| **Live** chain with the per-document Spark review visible, recorded 2026-10-31 (`evals/recorded/live-run-spark-review-2026-10-31.json`) | Full chain, same steps, with the review as its own provenance row (`read_invoice`: allow, flagging the hidden note as untrusted data); write attempts blocked by rules; stolen token `401`, crew `200` after refresh; USD 0.0810, 66.2 s run duration, 24.6 s from attack to first `401` driven by script with a synthetic voice file, so no human delay. Warehouse image is AI-generated test material |
| **Live** invoices ×20 (Spark 1.3 vision on rendered invoices) | Supplier/number/date/currency/subtotal/tax/total and arithmetic validation 20/20, USD 0.1812 |
| **Live** warehouse (SAM 3.1 synthetic images + Voice dictation) | Exact counts 4/4 with the precise prompt (`red rectangle`); with `red box` SAM returned 0 on the same images (1/4) — prompt wording matters and both are reported. Voice dictation parsed OK. USD 0.0100. No real warehouse footage yet |
| Exposure, confirmed (confidence ≥ 0.8) | Precision 1.000, recall 0.692 (TP 9, FP 0, FN 4). Before grouping sibling advisories: precision 0.643 (the twin PHP CVEs counted double). The 4 misses are Brotli, whose advisory has no parseable range: kept as candidates for Wonder triage, not invented as confirmed |
| Exposure, including candidates | Precision 0.765, recall 1.000 (TP 13, FP 4, FN 0) |
| Usage anomalies (synthetic 16 h abuse) | Precision 1.000, recall 1.000 (TP 32, FP 0, FN 0); 0 false positives on the normal series |
| Gateway overhead (local, instant fake upstream, 80 calls) | p50 1.74 ms, p95 2.48 ms (this run; see `evals/report.md`) |
| Invoices (20 synthetic, replay parser) | Total/number/arithmetic 20/20 |
| Warehouse (replay: synthetic SAM/voice outputs — no real footage yet) | Image count 3/3, video 3 unique track IDs, dictation and stock diff OK |
| Token rotation E2E (replay) | Attacker `200 → 401` in under 10 seconds (replay), other agents unaffected. The ~16 h figure is the October 2026 incident documented in `docs/DEMO.md`, not a live measurement |
| Spark Open gate | Not run — `needs_credits`: no Baseten key in the vault, so there is no live classifier number and none is estimated (see models table) |

## Meta models used

Evidence was checked with `grep` over `evals/recorded/` on 2026-10-31.
"Live call with recording" means a provenance step with that model and an
HTTP 200 in a recorded file. "Only in code" means the model is wired in
code but appears in no recording. "Not run" means no recording and a
missing key or credit, so no result is claimed.

| Model | Used for | Evidence |
|---|---|---|
| `muse-spark-1.3` | Guardian and crew reasoning, tool calling, invoice vision, per-document policy review, advisory intake | Live call with recording — provenance steps in `evals/recorded/live-run-2026-10-31.json`; also `heldout2-spark-*.json`, `spark-latency-2026-10-31.json` |
| `sam-3.1` | Warehouse counting (images; video track IDs in replay) via `/v1/responses` | Live call with recording — `count` and `contain` steps in `evals/recorded/live-run-2026-10-31.json` |
| `muse-voice-transcribe-1.0` | Voice approvals ("yes, rotate it") and warehouse dictation | Live call with recording — `voice` step in `evals/recorded/live-run-2026-10-31.json` |
| `muse-wonder-1.0` | Hard triage only: ambiguous exposures (`shield/exposure.py`) | Only in code — `grep` finds 0 occurrences in `evals/recorded/`; wired in `shield/exposure.py`, priced in `shield/meta_client.py`, probed by `scripts/smoke.py`. No recorded live call |
| `muse-image-1.0` | Test-material generation label for the warehouse image | Label only in the recording — `material_label` in `evals/recorded/live-run-2026-10-31.json` ("AI-generated test image (muse-image-1.0), not real warehouse footage"); no provenance step calls it. Priced/handled in `shield/meta_client.py`. No recorded live call as a model step |
| Muse Spark Open (`meta-models/muse-spark-open-1026`, Baseten, Modal fallback) | Output gate classifier (`shield/gate/open_classifier.py`) | Not run — needs credits: no Baseten key in the vault and 0 occurrences in `evals/recorded/`. No bonus and no result is claimed; the gate falls back to deterministic redaction and canaries |

Routes and prices were verified against the official docs; see
`docs/MODELS.md`. No `*-contributor` models are used.

## Built during the hackathon (26 Oct → 4 Nov 2026)

Checked against `git log` (PR merges #1–#13 plus the H14/H15 commits on
top).

| Pre-existing (not judged) | Built during the hackathon |
|---|---|
| No project code (initial commit only) | Skeleton, schemas, Meta client with replay (PR #1) |
| Business knowledge: how Purchasing and Warehouse actually work | Sandbox and evaluation sets (PR #2) |
| Existing accounts (Meta, GCP `bendrix-hackathon`, GitHub) | Gateway, vault, gate, policy and SDK (PRs #3, #4); lint cleanup (PR #5) |
| The October 2026 incident itself (the motivation, `docs/DEMO.md`) | Containment runbooks and self-healing SDK (PR #6) |
| | Crew, customer zero: Purchasing + Warehouse (PR #7) |
| | Guardian: watch, estate, exposure, anomaly (PR #8) |
| | WhatsApp/voice channels and owner panel (PR #9) |
| | Spark Open gate code, held-out eval, report (PR #10) — gate itself not run, needs credits |
| | Final integration: panel, held-out/exposure fixes, threat model, `make demo` (PR #11, H10) |
| | Live rounds with real models (invoices, SAM, Voice), held-out v2, hardening (PR #12, H11); brand (PR #13) |
| | Owner panel and live chain on real Meta models; held-out v2 with Spark recordings (`adf80f3`, `57b934d`) |
| | Per-document Spark review in the policy engine (`39c7069`); three arm-C runs recorded (`7820fb3`). Activation: `make live` sets `SHIELD_SPARK_REVIEW=on` (and the live chain also requires a real upstream key); `make demo` does not set it and runs in replay with the review off |

## Name and affiliation

Built on Meta's Muse models; independent project, not affiliated with
or endorsed by Meta. The public name is NoKey by default — it uses no
Meta trademark — and it lives in one place (`shield/brand.py`; change it
with `uv run python scripts/set_brand.py NUEVO_NOMBRE`). Brand assets
live in `docs/brand/`. The GitHub repository and Python package
(`bendrix_shield`) keep their original technical names — only the public
product name changed.

## License

MIT — see `LICENSE`.
