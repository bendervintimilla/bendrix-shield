"""Canarios: secretos trampa que jamás deben salir en un payload.

La lista trae una lista corta y sintética. La lista completa la reemplaza por `evals/canaries.json`
(10 secretos trampa) sin cambiar esta interfaz.
"""

from __future__ import annotations

DEFAULT_CANARIES: tuple[str, ...] = (
    "CANARY-SHIELD-0001",
    "sk-canary-shield-do-not-leak",
    "shd_canary_do_not_leak",
)


def find_canaries(text: str, canaries: tuple[str, ...] | list[str] | None = None) -> list[str]:
    pool = tuple(canaries) if canaries is not None else DEFAULT_CANARIES
    return [c for c in pool if c and c in text]
