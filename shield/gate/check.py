"""`gate.check(payload)` — hook obligatorio antes de todo envío saliente (SPEC §2.4).

En H1 es un stub honesto: busca canarios en la serialización del payload y
bloquea si aparece uno. H3 lo extiende con redacción determinista (regex de
llaves y PII) y el clasificador con Muse Spark Open, sin cambiar la firma.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from shield.gate.canaries import find_canaries


class GateBlocked(RuntimeError):
    """El payload contiene un canario y no debe salir."""


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    canaries_found: list[str] = field(default_factory=list)
    reason: str = ""


def _to_text(payload: object) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="ignore")
    try:
        return json.dumps(payload, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(payload)


def check(payload: object, *, canaries: list[str] | tuple[str, ...] | None = None) -> GateResult:
    found = find_canaries(_to_text(payload), canaries=tuple(canaries) if canaries else None)
    if found:
        return GateResult(allowed=False, canaries_found=found, reason="canary_in_payload")
    return GateResult(allowed=True, reason="ok")


def check_or_raise(payload: object, *, canaries: list[str] | tuple[str, ...] | None = None) -> None:
    result = check(payload, canaries=canaries)
    if not result.allowed:
        raise GateBlocked(f"gate blocked payload: canaries={result.canaries_found}")
