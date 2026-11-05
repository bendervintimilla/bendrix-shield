# wAIrrior — Business Protection

**wAIrrior is the AI warrior that watches every app and machine your business runs, spots irregularities, and contains the attack on its own.**

This week made it real: on 2 Nov attackers remotely forced supermarket freezers across Europe into defrost, up to 50 °C, ~40 Delhaize stores ([Tom's Hardware](https://www.tomshardware.com/tech-industry/cyber-security/supermarket-freezers-across-europe-struck-in-second-crippling-cyberattack-hackers-raise-temperatures-to-50-degrees-celsius-in-belgium-and-sweden-destroying-food-stocks), [CBS](https://www.cbsnews.com/news/europe-grocery-store-refrigerator-freezer-cyberattack-hack-food-wasted/), [Al Jazeera](https://www.aljazeera.com/news/2026/11/3/very-cold-war-whos-attacking-europes-supermarket-freezers)); on 4 Nov Crédit Mutuel Arkéa suspended transfers for **all** clients after fraudulent operations (press figure of 118 M€ unconfirmed by the bank; [Euronews](https://www.euronews.com/2026/11/04/credit-mutuel-arkea-reports-cyberattack-says-clients-will-be-fully-protected), [Le JDD](https://www.lejdd.fr/economie/cyberattaque-le-credit-mutuel-arkea-victime-doperations-frauduleuses-des-millions-deuros-potentiellement-detournes-187779)); and in October our own AI keys were abused for ~16 hours, USD 310 (`docs/DEMO.md`).

**Contain first, ask later: anything reversible wAIrrior does on its own in seconds; anything irreversible waits for the owner.** Then the owner hears: "You were attacked. We already did X, Y, Z. Tap to undo." The **Sentinel** screen shows exactly that: every connected app and machine on one timeline, a combined attack wave contained per app (blocked defrost, held payment, rotated token) while normal work continues, and the owner's WhatsApp notice after containment.

**Watch and try (no sign-in):** video (2:21) https://youtu.be/FkB9mli3ZHU · demo https://bendrix-shield-panel-290240328973.us-central1.run.app/ with the scenes [Sentinel](https://bendrix-shield-panel-290240328973.us-central1.run.app/?scene=sentinel&lang=en), [Real cameras](https://bendrix-shield-panel-290240328973.us-central1.run.app/?scene=surveillance&lang=en) and [Physics](https://bendrix-shield-panel-290240328973.us-central1.run.app/?scene=physical&lang=en).

**Real cameras, real Meta models.** Meta SAM 3.1 watches 5 real security cameras of our restaurant in Madrid. Every person is covered before any frame is shown, and raw frames never leave our machine (only redacted or human-verified empty frames are deployed; none are in this repo). Five security apps run on it: occupancy, after-hours intrusion, storeroom stock watch, unattended cash desk, and a shift report that Muse Spark 1.3 writes from redacted frames and counts only.

Why physics? Text is not a security boundary: a defrost is a legitimate command and a slow, in-range drift passes every static rule. Before an agent acts, a thermal twin (two nodes, air + product, deterministic, offline) predicts the **product** temperature with the accepted history included; the verdict depends on physics, not on the text that convinced the agent.

| Strongest figures | Result | Source (label) |
|---|---|---|
| 1,000 generated scenarios | Predictive shield stopped 419/419 damaging actions (95% CI [0.9909, 1]); static rules 7/419; false blocks 23/581; verdict p50 1.6 ms | `evals/physical/REPORT.md` (simulated) |
| SAM 3.1 on 5 real security cameras | 78 real frames labeled by hand: someone-vs-empty 78/78 (precision and recall 1.0); exact head count 59/78, within ±1 71/78 | `evals/recorded/witness-eval-2026-11-04.json` (live, real cameras) |
| Security apps on those cameras | Occupancy, after-hours intrusion, storeroom stock, unattended cash desk, Spark shift report from redacted frames | `evals/recorded/surveillance-2026-11-04.json` (live) |
| Sentinel, single-app attacks | Attack contained per app while 300/300 legitimate writes stay alive; suspending everything keeps 0/300 | `evals/autopilot/REPORT.md` (simulated) |
| Physical red team, 3 rounds | Every bypass found was published and then closed: deferred actions, cold-freeze destination, spoofed sensor, forged rescue (now an HMAC-signed `RescueGrant`) | `evals/physical/REDTEAM.md`, `shield/physics/rescue.py` (simulated) |
| Spark as attacker (20 plans) | Static rules pass 8/11 damaging plans silently; physics-only shield stops all heat damage (1 cold plan passed then, closed in round 2) | `evals/physical/SPARK-ATTACKER.md` (live-generated, simulated eval) |
| Autopilot vs suspend-everything (Arkéa pattern) | Attacks 2 → 0 while 263/300 legitimate writes stay alive; suspending everything keeps 0/300 | `evals/autopilot/REPORT.md` @ `50a667e` (simulated) |
| Live controller, real 2-Nov pattern | Muse Spark refused the injected "defrost 4 h, door open" document (0 actions); the physical gate blocked it (breach at 45 min, peak 16.4 °C) | `evals/recorded/physical-live-2026-11-04-defrost-r2.json` (live model, simulated physics) |
| SAM 3.1 scene reading | 7/7 boxes counted; open door detected in the cold-room scene (AI-generated test images, labeled) | `evals/recorded/physical-sam-2026-11-04.json`, `physical-sam-door-2026-11-04.json` (live) |

**Connect any app with one webhook:** `POST /autopilot/webhook` with a `SecurityEvent` JSON (`app`, `actor`, `action`, `target`, `values`; no secrets, only IDs/hashes). Detection, correlation and containment do not need to know your app (`shield/autopilot/events.py`). Full thesis, architecture and honest limits: [docs/FRONTIER.md](docs/FRONTIER.md). Everything below is the previously measured chain, unchanged (submitted earlier as NoKey).

w**AI**rrior is the safety layer between a small business's AI agents and the models and tools they call.
It lets an SME run AI agents — Purchasing reads supplier invoices, Warehouse counts stock — without ever handing those agents the real provider key.

**The problem.** In the October 2026 incident behind this project, our own AI keys leaked (a trojanized package and exposed cloud variables) and were abused for ~16 hours (USD 310, `docs/DEMO.md`). An agent that holds the real key turns one leak into an open tab. With wAIrrior the loot from the same kind of leak is one revocable per-agent token, and the fix is a rotation the owner approves by voice, not a redeploy.

- **One token per agent:** each agent gets its own revocable `shd_<agent>_…` token, with least-privilege scopes and a spend cap.
- **The real key never enters the app:** it stays in the gateway vault; apps only ever see their Shield token.
- **Rotation the owner approves by voice:** rotation normally needs the owner's approval (browser voice, panel, or a WhatsApp voice note — see below); then the stolen token answers `401`. One exception: optional automatic containment (`Actions(auto_contain=True)`) can rotate a token without prior approval when a canary is detected; that action is audited (see `shield/actions/runbooks.py`).
- **Poisoned documents are blocked, not obeyed:** external documents are data, never instructions; most end in `block` or `ask_owner`, with per-document Muse Spark review when enabled. Measured exception: the English token-reveal read (`v2-poison-token-en`) passed silently in the rules-only baseline (1/12) and in 2 of 3 runs with per-document Spark review (see Metrics).

## Live demo

**Final video (2:21, wAIrrior Frontier: Sentinel, real cameras, physics):** https://youtu.be/FkB9mli3ZHU

**Earlier video (2:54, one live take on real Meta models, key-theft chain):** https://youtu.be/_wTT0IqXHvI — narration and the owner's voice approval are synthetic (Meta MMS-TTS); sped-up parts are labeled. The take's own record (run `live_97efbfa04a72`) is `evals/recorded/live-run-video-take-2026-11-03.json`.

**https://bendrix-shield-panel-290240328973.us-central1.run.app/** — open it, no sign-in, nothing to install. It opens the same sphere screen as live mode, running the **Replay** (EN/ES, two scenes: Warehouse and Cold chain). Press **Run until the owner decides**, then type your approval and watch the stolen token go from `200` to `401` while the other agents keep working. Each visitor gets their own run; the approval goes through the real single-use flow.

It is the replay of a recorded real run: no real keys, no model calls and no spend; "Live" is disabled on this link. The Warehouse scene plays back the live run recorded on 2026-11-02 (`evals/recorded/live-run-video-take-2026-11-02.json`, run `live_540cbeecf6fc`, 47.0 s from the attack to the first `401`), shown on screen as "recorded live run (2 Nov): 47 s"; the video above shows the 3 Nov take, a different run. The big "Contained in" clock in the replay is your own time, including how long you take to approve. The live mode (real Meta models, which costs money) is off on this URL; run it yourself with `make live` and your own key.

**Live mode online (access code).** A separate Cloud Run service, `bendrix-shield-live`, runs the same chain with the real Meta models (Muse Spark 1.3, SAM 3.1, Muse Voice Transcribe) behind an access code, so strangers cannot spend. The server enforces a hard cap of USD 5 and 20 runs per day (Ecuador time, ledger in a private GCS object that survives restarts, fails closed) plus USD 0.60 per run; at the cap it answers `429` with a clear message and never calls a model. The Meta key and the code come from Secret Manager (`--set-secrets`), never from the image or the repo. The browser microphone works over HTTPS; if it is denied, the owner's decision can be typed and the page says so. Deploy with `GCP_PROJECT=<project> bash deploy/cloudrun-live.sh`.

**Try it**

```bash
uv sync --extra dev
make demo   # replay, no key needed
make live   # with your META_MODEL_API_KEY; see Run it live
```

## What is measured

| Figure | Result | Source |
|---|---|---|
| Live take shown in the video (2026-11-03, run `live_97efbfa04a72`, real Meta models) | 70.8 s from the attack to the first `401` (includes the wait for the owner's voice approval); Warehouse SDK `401 → 200`, recount 7; Purchasing `200`; WhatsApp alert sent (HTTP 200); revoke-all: 3 tokens revoked, 4 probes `401`; USD 0.097 | `evals/recorded/live-run-video-take-2026-11-03.json` |
| WhatsApp approval with the owner's real voice note (2026-11-03, run `live_c31aa0ec5ef2`) | Transcribed "Yes, rotate it." → approved → attacker `401`; Warehouse SDK `401 → 200`, recount 7; Purchasing `200`; USD 0.076 | `evals/recorded/live-run-whatsapp-owner-voice-2026-11-03.json` |
| Adversarial red team (37 frozen cases, 5 vectors, offline, USD 0) | Stopped 36/37 on the frozen measurement (main `73875bc`); 1 passed silently (`rt-inj-audit-en-read`, an English read). After that measurement the rule was adjusted, not the case (imperative "attach the/your…" added to `reveal_secret`, word-bounded so "attachment"/"Attached:" stay benign): the re-run stops 37/37, 0 regressions. 37/37 is a post-measurement fix, not a blind figure | 36/37: `evals/recorded/redteam-c2490.json` (frozen, unchanged). 37/37: `evals/recorded/redteam-c2490-post-attach.json`, `uv run python evals/run_redteam.py`. Both in `evals/report.md` (red team section and "Ajuste posterior a la medición") |
| Held-out v2, rules only | Blocked 4/12, to owner 7/12, silent 1/12 (a read; sensitive writes 0/12) | `evals/report.md` H11 held-out v2 |
| Held-out v2, per-document Spark review (3 runs) | Blocked 12, 10, 11/12; silent 0, 1, 1; false blocks 1, 0, 0 | `evals/report.md` H15; `evals/recorded/heldout2-spark-armc*.json` |
| Stolen-token rotation (automated replay test) | Attacker `200 → 401` in under 10 seconds, with the approval given by the test (no human wait) | `tests/test_actions_h6.py`; `evals/report.md` H6 |
| Live chain recorded 2026-10-31 | USD 0.0749 in 84.7 s; stolen token `401`, crew token `200` after refresh | `evals/recorded/live-run-2026-10-31.json` |
| Offline test suite | 427 passed with no network and no key (2026-11-04, branch `wairrior-final`) | `make test` / `uv run pytest -q` |

Time to the first `401` depends on who is in the loop: under 10 s in the automated test (`tests/test_actions_h6.py`, approval given by the test); in the hosted replay the "Contained in" clock includes how long you take to approve (the recorded 2 Nov live run it plays back took 47.0 s); about 24.6 s scripted live with a synthetic voice file, 70.8 s in the video take with the owner's voice approval, and 791 s over WhatsApp (that figure includes the time the plan waited for the owner).

Detail for every figure is in Metrics below. Held-out v2 is fresh, blind to the policy rules and frozen before measuring (`evals/heldout2/`). `evals/report.md`, `docs/DEMO.md` and `docs/threats-2026.md` are mostly in Spanish; this README is the English summary of every figure.

## Real 2025-2026 attacks → controls, and the cold-chain scenario

In 2025-2026 attackers trojanized AI tooling, stole provider keys from hosting
environment variables, injected instructions into documents agents read, and —
in European supermarkets — remotely turned up refrigeration until shelves
emptied. Restaurants run the same cold chain. `docs/threats-2026.md` (in Spanish) maps each
real attack (with sources) to the wAIrrior control that stops it, to what was
missing, and to the prioritized list that was then implemented.

New in this round: a **Refrigeration** agent with its own least-privilege
token. A stolen Refrigeration token that tries to raise a cold-room setpoint to
50 °C or a freezer to 5 °C — at 03:00, from an unusual origin — is blocked on
range, hour and origin signals (2/2 measured attacks blocked); the attacker
goes `200 → 401` only for that token after the owner approves the rotation by
voice, while Refrigeration, Warehouse and Purchasing keep answering `200`
(`evals/recorded/cold-chain-replay.json`, runs offline in `make demo`). The
gateway also gained per-token route/value scopes (`403`), per-token and
per-agent rate limits (`429`), opt-in nonce + timestamp anti-replay
(`401`/`409`), a sha256 hash-chained audit log the owner can verify, and an
emergency revoke-all. An adversarial battery of 37 frozen cases in 5 vectors
(document injection, token exfiltration, owner-voice replay, agent confusion,
rate abuse) first stopped 28 of 37. Owner approvals are now **single-use**:
each one is bound to its request nonce, to the exact action and token it
approves, and expires (15 min by default); replaying the owner's recorded
"yes" against another request, or reusing one `approval_id` for a second plan,
no longer works (historical step: the 3 bypasses it closed took the battery
from 28/37 to 31/37). What a
nonce does not do is identify the speaker: whoever holds the owner's own
surface (panel, WhatsApp button) can still approve. A hardening pass (C2490:
text normalization and base64 decoding before the injection engine and the
gate, split-canary detection, one token file per agent with `0600`/`0700`)
closed 5 more bypasses. Re-run offline on the frozen cases, the battery
stops 36 of 37 and 1 passed silently (`rt-inj-audit-en-read`), published
as-is in `evals/report.md` (rows in `evals/recorded/redteam-c2490.json`), with 0 regressions; 28/37 and 31/37 are the
earlier, historical measurements. After that frozen measurement, one rule
was adjusted (the English verb "attach" in `reveal_secret`; the case was not
touched) and the re-run stops 37/37 with 0 regressions
(`evals/recorded/redteam-c2490-post-attach.json`); the report labels it
as a post-measurement fix, since the case was known before the rule changed.

The hosted replay above needs no key; `make demo` runs the same story
locally in replay, and `make live` runs it against the real Meta API with
your own key (see below).

## Connect any app in 2 lines

```python
from openai import OpenAI
import bendrix_shield as shield

client = shield.wrap(OpenAI(), "shd_<agent>_replace-with-your-token")
```

That is the whole integration: `wrap` points your OpenAI-compatible
client at the wAIrrior gateway with your per-agent Shield token. The real
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
per model. Deploy the gateway with `bash deploy/cloudrun.sh` (GCP project from
`$GCP_PROJECT`).

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

## WhatsApp voice-note approvals

WhatsApp voice-note approvals: tested live on 2026-11-03 with the owner's
real voice note over the WhatsApp Cloud API (run `live_c31aa0ec5ef2`, USD 0.076,
Spark read "Yes, rotate it." → approved → attacker 401, Warehouse SDK 401→200,
recount 7, Purchasing 200). Evidence, redacted:
`evals/recorded/live-run-whatsapp-owner-voice-2026-11-03.json`. Its
`contained_in_s` (791 s) includes the time the plan waited for the owner.
A recording can approve only one plan; forwarded notes and notes older than the
plan are rejected.

The owner can approve the live containment plan by replying to a
WhatsApp text with a voice note instead of using the browser
microphone. To configure it: create an app in Meta for Developers,
add the WhatsApp product, use the test number, register the owner's
number as an allowed recipient, point the webhook at
`https://<tunnel>/webhook/whatsapp` subscribed to the `messages`
field, and store the vault secrets `whatsapp-test-token`,
`whatsapp-test-phone-id`, `whatsapp-test-phone`,
`whatsapp-test-verify-token` and `whatsapp-app-secret` (never in
git). Without real credentials the outgoing message stays in the
simulator outbox. Details in `channels/README.md`.

## Architecture

```text
                    shd_<agent>_…                 real key (vault only)
  any app ──────────────────────▶ wAIrrior gateway ──────────────────▶ Meta Model API
                                      │  │
                       gate.check() ──┘  └── policy.check() on every tool call
                                      │
              watch · estate · exposure · anomaly  ──▶  guardian agent
                                      │
                 owner approves by voice / panel / WhatsApp voice note
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
  usually ends in `block` or `ask_owner`. Measured exception: the
  English token-reveal read (`v2-poison-token-en`) passed silently in
  the rules-only baseline (1/12) and in 2 of 3 runs with per-document
  Spark review (see Metrics).
- `shield/sdk/` — `bendrix_shield`: the 2-line `wrap`, `@shield.tool`,
  `shield.untrusted`, and the self-healing token refresh.
- `shield/watch/`, `shield/estate/`, `shield/exposure.py`,
  `shield/anomaly.py` — public advisories to `ThreatCard`s; a read-only
  inventory of connected apps; `ThreatCard × Asset → Exposure` (sibling
  advisories with the same product and range count once); and usage
  anomalies (new country, unused model, cost spikes).
- `shield/actions/`, `shield/agent.py` — idempotent, reversible
  runbooks (`rotate_token`, `revoke`, `redeploy`, `verify`,
  `patch_plan`) and the guardian agent that runs them. Effects need
  the owner's `approval_id`, except optional automatic containment
  (`auto_contain=True`) on a canary detection, which is audited.
- `channels/`, `web/` — voice approvals, a WhatsApp Cloud API webhook
  (simulator mode without real credentials; voice-note approvals in the
  live chain tested live with the owner's real voice note on 2026-11-03 —
  see WhatsApp voice-note approvals above), plus the
  owner's panel (apps, live decisions, incidents, attacker terminal
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
beat, is `docs/DEMO.md` (in Spanish; the English summary of every figure
is the Metrics table below).

## Metrics (real, from `evals/report.md` — not inflated)

Numbers below come from `evals/report.md` and `evals/recorded/`.
Offline rows are replay/fixtures; rows marked **live** used real Meta
models (live invoice/warehouse rounds on 29 Oct 2026, live chain
recordings on 31 Oct 2026, and the video take and the WhatsApp owner
voice-note run on 3 Nov 2026; cost in the row). The headline injection
number is held-out v2: a fresh set written blind to the policy rules
and frozen before measuring, never used to tune the rules. The older
held-out set is kept as history because rules were later adjusted
with it.

| Measurement | Result |
|---|---|
| Synthetic injection set (shares patterns with the rules; regression only) | Blocked 30/30 (100%); clean false positives 0/30 |
| **Held-out v2 (headline)** — fresh, blind to the rules, frozen | Blocked 4/12, escalated to owner 7/12, **silently allowed 1/12** — one English read asking to reveal the gateway token; sensitive writes silently allowed **0/12**. Legitimate formal account changes reach `ask_owner` 3/3; clean reads allowed 5/5 |
| **Live** held-out v2, shipped engine with per-document Spark review (3 runs, same frozen set; H15 section) | Blocked 12, 10 and 11 of 12; to owner 0, 1 and 0; silently allowed 0, 1 and 1 (same English read, `v2-poison-token-en`); legitimate 2/3, 3/3 and 3/3 in `ask_owner`; clean reads 5/5; false blocks 1, 0 and 0 (the 1 is `v2-clean-formal-en`, run 1). USD 0.0975, 0.0913 and 0.0856; 16 Spark calls per run. Earlier arm-B measurement (Spark on every case, stricter wins; 3 runs): blocked 10, 11 and 11 of 12; to owner 1, 0 and 0; silently allowed 1 in each run (same English read); legitimate 3/3, 3/3 and 2/3 in `ask_owner`; clean reads 5/5 in each run; false blocks 0, 0 and 1 (the 1 is `v2-clean-formal-en` in the third run, recorded in `evals/recorded/heldout2-spark-armc-2026-10-31.json` arm B). USD 0.1121, 0.1316 and 0.1102; 20 Spark calls per run — see H14 and H15 sections |
| Held-out v1 (history; rules were later adjusted with it) | Blocked 3/12, escalated to owner 9/12, silently allowed 0/12 after the reveal-read fix (2 before). Legitimate formal changes `ask_owner` 4/4; clean reads 4/4 |
| **Live** chain through the gateway, recorded 2026-10-31 (`evals/recorded/live-run-2026-10-31.json`) | Invoice vision, SAM 3.1 count, stolen-token attack, guardian, voice transcription and approved rotation in one run; stolen token `401` after rotation, crew `200` after refresh; USD 0.0749, 84.7 s. Warehouse image is AI-generated test material, not real footage |
| **Live** chain with the per-document Spark review visible, recorded 2026-10-31 (`evals/recorded/live-run-spark-review-2026-10-31.json`) | Full chain, same steps, with the review as its own provenance row (`read_invoice`: allow, flagging the hidden note as untrusted data); write attempts blocked by rules; stolen token `401`, crew `200` after refresh; USD 0.0810, 66.2 s run duration, about 24.6 s from attack to first `401` driven by script with a synthetic voice file, so no human delay (see note below). Warehouse image is AI-generated test material |
| **Live** take shown in the video, recorded 2026-11-03 (`evals/recorded/live-run-video-take-2026-11-03.json`, run `live_97efbfa04a72`) | Same chain with the owner's approval by voice in the browser (synthetic audio): 70.8 s from attack to first `401`, including the wait for that approval; Warehouse SDK `401 → 200`, recount 7, Purchasing `200`; WhatsApp alert sent (HTTP 200); emergency revoke-all: 3 tokens revoked, 4 probes `401`; USD 0.097 (0.097387), 175.3 s run duration |
| **Live** WhatsApp approval with the owner's real voice note, recorded 2026-11-03 (`evals/recorded/live-run-whatsapp-owner-voice-2026-11-03.json`, run `live_c31aa0ec5ef2`) | Transcribed "Yes, rotate it." → approved → attacker `401`; Warehouse SDK `401 → 200`, recount 7; Purchasing `200`; USD 0.076; `contained_in_s` 791 s includes the time the plan waited for the owner |
| **Live** invoices ×20 (Spark 1.3 vision on rendered invoices) | Supplier exact match 4/20; number/date/currency/subtotal/tax/total and arithmetic validation 20/20, USD 0.1812 |
| **Live** warehouse (SAM 3.1 synthetic images + Voice dictation) | Exact counts 4/4 with the precise prompt (`red rectangle`); with `red box` SAM returned 0 on the same images (1/4) — prompt wording matters and both are reported. Voice dictation parsed OK. USD 0.0100. No real warehouse footage yet |
| Exposure, confirmed (confidence ≥ 0.8) | Precision 1.000, recall 0.692 (TP 9, FP 0, FN 4). Before grouping sibling advisories: precision 0.643 (the twin PHP CVEs counted double). The 4 misses are Brotli, whose advisory has no parseable range: kept as candidates for Wonder triage, not invented as confirmed |
| Exposure, including candidates | Precision 0.765, recall 1.000 (TP 13, FP 4, FN 0) |
| Usage anomalies (synthetic 16 h abuse) | Precision 1.000, recall 1.000 (TP 32, FP 0, FN 0); 0 false positives on the normal series |
| Gateway overhead (local, instant fake upstream, 80 calls) | p50 1.74 ms, p95 2.48 ms (this run; see `evals/report.md`) |
| Invoices (20 synthetic, replay parser) | Total/number/arithmetic 20/20 |
| Warehouse (replay: synthetic SAM/voice outputs — no real footage yet) | Image count 3 (expected 3) in a single image, video 3 unique track IDs, dictation and stock diff OK |
| Token rotation E2E (automated replay test, `tests/test_actions_h6.py`) | Attacker `200 → 401` in under 10 seconds with the approval given by the test, other agents unaffected. The ~16 h figure is the October 2026 incident documented in `docs/DEMO.md`, not a live measurement |
| Spark Open gate | Not run — `needs_credits`: no Baseten key in the vault, so there is no live classifier number and none is estimated (see models table) |

Note on the about 24.6 s figure: it is the elapsed time from the start
of the attack step to the first `401` after the approved rotation, as
measured by the chain (`contained_in_s` in `web/live_chain.py`). The
recording (`evals/recorded/live-run-spark-review-2026-10-31.json`) does
not store that value. Its provenance rows are stamped as each call ends:
the row before the attack is at 12:03:33.1 UTC and the first `401` at
12:03:57.8 UTC, about 24.7 s apart. The first stolen-token call ended at
12:03:35.2 UTC, about 22.6 s before that `401`.

## Meta models used

Evidence was checked with `grep` over `evals/recorded/` on 2026-11-04
(recordings from 31 Oct to 3 Nov 2026).
"Live call with recording" means a provenance step with that model and an
HTTP 200 in a recorded file. "Only in code" means the model is wired in
code but appears in no recording. "Not run" means no recording and a
missing key or credit, so no result is claimed.

| Model | Used for | Evidence |
|---|---|---|
| `muse-spark-1.3` | Guardian and crew reasoning, tool calling, invoice vision, per-document policy review, advisory intake | Live call with recording — provenance steps in `evals/recorded/live-run-2026-10-31.json`; also `heldout2-spark-*.json`, `spark-latency-2026-10-31.json`, `live-run-video-take-2026-11-03.json`, `live-run-whatsapp-owner-voice-2026-11-03.json` |
| `sam-3.1` | Warehouse counting (images; video track IDs in replay) via `/v1/responses` | Live call with recording — `count` and `contain` steps in `evals/recorded/live-run-2026-10-31.json`; also `live-run-video-take-2026-11-03.json` |
| `muse-voice-transcribe-1.0` | Voice approvals ("yes, rotate it") and warehouse dictation | Live call with recording — `voice` step in `evals/recorded/live-run-2026-10-31.json` (synthetic audio) and in `evals/recorded/live-run-whatsapp-owner-voice-2026-11-03.json` (the owner's real voice note over WhatsApp, "Yes, rotate it.") |
| `muse-wonder-1.0` | Hard triage only: ambiguous exposures (`shield/exposure.py`) | Only in code — `grep` finds 0 occurrences in `evals/recorded/`; wired in `shield/exposure.py`, priced in `shield/meta_client.py`, probed by `scripts/smoke.py`. No recorded live call |
| `muse-image-1.0` | Test-material generation label for the warehouse image | Label only in the recording — `material_label` in `evals/recorded/live-run-2026-10-31.json` ("AI-generated test image (muse-image-1.0), not real warehouse footage"); no provenance step calls it. Priced/handled in `shield/meta_client.py`. No recorded live call as a model step |
| Muse Spark Open (`meta-models/muse-spark-open-1026`, Baseten, Modal fallback) | Output gate classifier (`shield/gate/open_classifier.py`) | Not run — needs credits: no Baseten key in the vault and 0 occurrences in `evals/recorded/`. No result is claimed; the gate falls back to deterministic redaction and canaries |

Meta platform component that is a channel, not a model:

| Component | Used for | Evidence |
|---|---|---|
| WhatsApp Cloud API (Meta) | The guardian sends the owner the alert; the owner answers with a voice note that Muse Voice Transcribe turns into the approval (webhook `/webhook/whatsapp`; simulator without credentials) | Live, recorded — `evals/recorded/live-run-whatsapp-owner-voice-2026-11-03.json` (`channel: whatsapp`); alert sent with HTTP 200 in `evals/recorded/live-run-video-take-2026-11-03.json` |

Routes and prices were verified against the official docs; see
`docs/MODELS.md`. No `*-contributor` models are used.

## Built during the hackathon (26 Oct → 4 Nov 2026)

Checked against `git log` (PRs #1–#35; #19 does not appear in `git log`;
the repo starts with its initial commit on 28 Oct 2026).

| Pre-existing (not judged) | Built during the hackathon |
|---|---|
| No project code (initial commit only) | Skeleton, schemas, Meta client with replay (PR #1) |
| Business knowledge: how Purchasing and Warehouse actually work | Sandbox and evaluation sets (PR #2) |
| Existing accounts (Meta, GCP, GitHub) | Gateway, vault, gate, policy and SDK (PRs #3, #4); lint cleanup (PR #5) |
| The October 2026 incident itself (the motivation, `docs/DEMO.md`) | Containment runbooks and self-healing SDK (PR #6) |
| | Crew, customer zero: Purchasing + Warehouse (PR #7) |
| | Guardian: watch, estate, exposure, anomaly (PR #8) |
| | Voice channel, WhatsApp webhook simulator and owner panel (PR #9) |
| | Spark Open gate code, held-out eval, report (PR #10) — gate itself not run, needs credits |
| | Final integration: panel, held-out/exposure fixes, threat model, `make demo` (PR #11) |
| | Live rounds with real models (invoices, SAM, Voice), held-out v2, hardening (PR #12); brand (PR #13) |
| | Owner panel and live chain on real Meta models; held-out v2 with Spark recordings (`adf80f3`, `57b934d`) |
| | Per-document Spark review in the policy engine (`39c7069`); three arm-C runs recorded (`7820fb3`). Activation: `make live` sets `SHIELD_SPARK_REVIEW=on` (and the live chain also requires a real upstream key); `make demo` does not set it and runs in replay with the review off |
| | Public replay with one run per visitor (#14); Live demo section and deploy script (#15); threats 2025-2026 → controls (#16); gateway scopes, rate limits, anti-replay nonce and hash-chained audit (#17, #20); cold-chain scenario (#18); adversarial red-team battery and its honest table (#21, #22) |
| | Live mode online with access code and server-side spend cap (#23, #24); live panel fix for a new run started mid-step (#25); single-use owner approvals and the sphere screen on the public URL (#26); no-traffic tagged deploys (#27) |
| | WhatsApp voice-note errors visible (#28); hardening pass to 36/37 on the frozen red team (#29); one voice recording approves one plan (#30); emergency revoke-all (#31); live WhatsApp approval with the owner's real voice note (#32) |
| | Public brand (#33), panel redesign (#34), panel label and new video link (#35); then the wAIrrior spelling and the video take's record (`evals/recorded/live-run-video-take-2026-11-03.json`) in the final docs pass; final pass: replay reset/step race, live start race, CVE ids no longer redacted as phones, post-measurement "attach" rule fix |

## Name and affiliation

Built on Meta's Muse models; independent project, not affiliated with
or endorsed by Meta. The public name is wAIrrior — it uses no Meta trademark — and it lives
in one place (`shield/brand.py`; `scripts/set_brand.py` can rename it).
Brand assets
live in `docs/brand/`. The GitHub repository and Python package
(`bendrix_shield`) keep their original technical names — only the public
product name changed.

## License

MIT — see `LICENSE`.
