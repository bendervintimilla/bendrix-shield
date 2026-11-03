"""Alcance mínimo por token (C2489-3): verbo + ruta y rangos de valores.

Gramática de rutas (``allowed_routes`` o scopes con forma de ruta):
- ``"POST /v1/chat/completions"`` o ``"POST:/v1/chat/completions"``: verbo y ruta.
- ``"/v1/chat/completions"``: solo ruta, cualquier verbo.
- Sufijo ``/*``: prefijo, p. ej. ``"POST /v1/*"``.
- ``"*"``: todo. Lista vacía: sin restricción (compatibilidad hacia atrás).

Scopes legados sin ``/`` (p. ej. ``"crew"``) no se tratan como rutas y no
restringen nada por esta vía. Rangos: ``numeric_limits`` mapea nombre de
campo a ``[mín, máx]`` y se revisa en todo el payload (también anidado).
"""

from __future__ import annotations

import math
from typing import Any

from shield.schemas import AgentToken


def _parse_route(entry: str) -> tuple[str | None, str]:
    e = entry.strip()
    if e == "*":
        return None, "*"
    if ":" in e and "/" in e and e.split(":", 1)[0].replace("-", "").isalpha():
        verb, _, path = e.partition(":")
        return verb.strip().upper() or None, path.strip()
    if " " in e:
        verb, _, path = e.partition(" ")
        return verb.strip().upper() or None, path.strip()
    return None, e


def _route_entries(token: AgentToken) -> list[tuple[str | None, str]]:
    entries: list[tuple[str | None, str]] = [_parse_route(r) for r in token.allowed_routes]
    for scope in token.scopes:
        if "/" in scope:  # solo scopes con forma de ruta restringen rutas
            entries.append(_parse_route(scope))
    return entries


def route_allowed(token: AgentToken, method: str, path: str) -> bool:
    entries = _route_entries(token)
    if not entries:
        return True
    verb = method.upper()
    for want_verb, want_path in entries:
        if want_path == "*":
            return True
        if want_verb is not None and want_verb != verb:
            continue
        if want_path.endswith("/*"):
            if path.startswith(want_path[:-1]):
                return True
        elif path == want_path:
            return True
    return False


def _walk_numbers(value: Any, key: str | None = None):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _walk_numbers(v, str(k))
    elif isinstance(value, list):
        for v in value:
            yield from _walk_numbers(v, key)
    elif isinstance(value, bool):
        return
    elif isinstance(value, (int, float)) and key is not None:
        yield key, float(value)


def check_numeric_limits(token: AgentToken, payload: Any) -> str | None:
    """Devuelve el campo fuera de rango, o None si todo está dentro."""
    if not token.numeric_limits:
        return None
    normalized = {str(k).lower(): v for k, v in token.numeric_limits.items()}
    for key, number in _walk_numbers(payload):
        bounds = normalized.get(key.lower())
        if bounds is None or len(bounds) != 2:
            continue
        lo, hi = float(bounds[0]), float(bounds[1])
        if not math.isfinite(number) or number < lo or number > hi:
            return key
    return None
