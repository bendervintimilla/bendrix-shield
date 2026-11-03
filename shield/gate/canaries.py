"""Canarios: secretos trampa que jamás deben salir en un payload.

La lista trae una lista corta y sintética. La lista completa la reemplaza por `evals/canaries.json`
(10 secretos trampa) sin cambiar esta interfaz.
"""

from __future__ import annotations

from shield.textnorm import compact

DEFAULT_CANARIES: tuple[str, ...] = (
    "CANARY-SHIELD-0001",
    "sk-canary-shield-do-not-leak",
    "shd_canary_do_not_leak",
)

# Largo mínimo de la forma compacta (solo letras y dígitos) para buscar un
# canario sin separadores: por debajo, palabras comunes darían falsos positivos.
MIN_COMPACT_LEN = 12


def find_canaries(text: str, canaries: tuple[str, ...] | list[str] | None = None) -> list[str]:
    pool = tuple(canaries) if canaries is not None else DEFAULT_CANARIES
    return [c for c in pool if c and c in text]


def find_canaries_compact(
    text: str, canaries: tuple[str, ...] | list[str] | None = None
) -> list[str]:
    """Canarios presentes al quitar espacios y separadores (y sin mayúsculas).

    Caza ``CANARY- SHIELD -0001`` o un canario partido en varias cadenas.
    Solo para canarios cuya forma compacta tenga ``MIN_COMPACT_LEN`` o más.
    """
    pool = tuple(canaries) if canaries is not None else DEFAULT_CANARIES
    flat = compact(text)
    out = []
    for c in pool:
        key = compact(c) if c else ""
        if len(key) >= MIN_COMPACT_LEN and key in flat:
            out.append(c)
    return out
