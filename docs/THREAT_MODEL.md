# Threat model — token refresh and what a thief actually gets

This note closes the H6 review point: the SDK refreshes a rotated Shield
token from the agent's local store so the crew keeps working with no
redeploy. That convenience is only safe if we are precise about **which**
secret the attacker stole. The demo and the README use this same wording.

## The two different thefts

| What the attacker steals | What they get | What they do **not** get | What happens next |
|---|---|---|---|
| The Shield token in an environment variable, a leaked log line, or a copied config value (`shd_<agent>_…`) | That one token, for that one agent, with that agent's scopes and spend cap, until it is rotated or revoked | The local token store (`~/.shield/agent-tokens.json`, mode `0600`), the real provider key (vault only), and the service identity of the workload | The guardian rotates that agent's token. The stolen copy gets `401`; the legitimate workload refreshes from its local store and keeps working (Bodega keeps counting). Other agents are untouched: one agent = one token = one scope |
| The local token store itself (the file on the agent's host, or the host) | Whatever the store holds, including the ability to refresh after a rotation, plus anything else that host compromise implies | Still not the real provider key (it never leaves the vault/gateway), and still not other agents' stores on other hosts | This is a host compromise, not a token leak. Rotating the token alone is not enough: revoke the agent, re-issue on a clean host, and treat the host as breached |
| The service identity (Cloud Run service account, only if the platform identity itself is compromised) | The ability to satisfy an identity-bound refresh check (below) and whatever that service account may call in `bendrix-hackathon` | The vault's other secrets by itself: Secret Manager access is per-secret IAM, and the panel service carries no write secrets at all | Revoke/rotate at the platform layer (disable the service account, re-deploy with a new one). Shield token rotation alone does not fix a stolen platform identity |

The Black October shape — exposed environment variables on a hosting
platform — is the **first** row. Shield is built so that row is cheap:
the loot is one revocable token, not the provider key, and the fix is a
rotation measured in seconds, not a 16-hour abuse window.

## Rules that follow from this

1. **Apps never hold the real provider key.** Only the gateway reads it
   from the vault. A stolen Shield token never upgrades into the
   provider key.
2. **The refresh path is local and per agent.** `LocalTokenStore` lives
   on the agent's own host with `0600` permissions and is never
   committed. Whoever only copied an env var cannot follow a rotation.
3. **Rotation is per agent.** Rotating Bodega does not take Compras
   down, and revoking the stolen token does not wait for a redeploy.
4. **The panel holds no write secrets.** The public panel runs with
   `DEMO=replay` and no `--set-secrets` write credentials; it can show
   the incident, but it cannot mint or rotate real tokens.

## Cheap hardening shipped in H10: bind refresh to service identity

When a deployment sets `SHIELD_EXPECTED_SERVICE_ACCOUNT` (or passes
`expected_service_account=` to `ShieldClient` / `refresh_client_token`),
the SDK only refreshes if the workload's service-account email — read
from the Cloud Run/GCE metadata server — equals the expected one. If
the identity differs, or cannot be confirmed, refresh fails closed and
the stale token keeps getting `401` instead of silently following the
rotation. Locally and in replay the variable is unset, so the H6
behaviour is unchanged; the check costs one metadata call per refresh
attempt (refresh only happens after a `401`, never per request).

This does **not** make a stolen store safe — row two above still holds.
It narrows row one further on Cloud Run: code running under a different
service account cannot ride along with a rotation even if it can read
the store file through some other bug.

## Out of scope

- No production systems: only the `bendrix-hackathon` project and the
  sandbox (SPEC invariant 1).
- The attacker in the demo uses our own test tokens against our own
  gateway; there is no scanning or exploitation of third parties.
- WhatsApp/voice approval proves the owner said yes on that channel;
  channel-account compromise is a separate model and the panel remains
  the fallback approver.
