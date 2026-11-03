"""g · Revocación de emergencia visible en la demo.

No duplica la lógica: llama al endpoint real del gateway `POST /shield/revoke-all`
(`Registry.revoke_all`) con la llave de emergencia de esa corrida y luego prueba cada
token contra el mismo gateway para mostrar el 401.

La prueba usa un modelo que no existe en ninguna lista permitida: aunque un token
siguiera activo, el gateway lo frena antes de llamar a Meta. Además, si el registro
dice que un token sigue activo, no se manda la prueba.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from shield.registry import Registry
from shield.schemas import AgentTokenStatus

PROBE_MODEL = "nokey-revocation-probe"


def run_emergency_revoke(
    client: httpx.Client,
    emergency_token: str,
    probes: list[tuple[str, str]],
    *,
    registry: Registry | None = None,
) -> dict[str, Any]:
    """Revoca todos los tokens activos y comprueba que cada uno da 401."""
    started = time.perf_counter()
    resp = client.post("/shield/revoke-all", headers={"x-shield-emergency": emergency_token})
    try:
        body = resp.json()
    except Exception:
        body = {}
    if resp.status_code != 200:
        err = body.get("error") if isinstance(body, dict) else None
        message = err.get("message") if isinstance(err, dict) else None
        return {
            "status": "error",
            "error": message or f"revoke-all returned {resp.status_code}",
            "http_status": resp.status_code,
        }
    revoked = int(body.get("revoked") or 0)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for label, raw in probes:
        if not raw or raw in seen:
            continue
        seen.add(raw)
        if registry is not None:
            tok = registry.authenticate(raw)
            if tok is not None and tok.status is AgentTokenStatus.ACTIVE:
                rows.append({"agent": label, "status": None, "code": "still_active"})
                continue
        r = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw}"},
            json={"model": PROBE_MODEL, "messages": [{"role": "user", "content": "probe"}]},
        )
        try:
            err = (r.json() or {}).get("error") or {}
            code = err.get("code") if isinstance(err, dict) else None
        except Exception:
            code = None
        rows.append({"agent": label, "status": r.status_code, "code": code})
    all_locked = bool(rows) and all(row["status"] == 401 for row in rows)
    return {
        "status": "ok" if all_locked else "error",
        "error": "" if all_locked else "a token still answers after revoke-all",
        "revoked": revoked,
        "probes": rows,
        "all_locked": all_locked,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
    }
