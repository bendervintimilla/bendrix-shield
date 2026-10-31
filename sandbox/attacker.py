#!/usr/bin/env python3
"""Atacante de la Cantina Demo: reusa un token de PRUEBA contra el gateway PROPIO.

Jamás apunta fuera de allowlist.yaml (defensa pura). Sin red real en
tests: la URL por defecto es localhost y los tests usan un transporte falso.
Uso: SHIELD_TOKEN_CREW_BODEGA=<token-demo> python sandbox/attacker.py --attempts 3
Tras rotar el token en el panel, el mismo comando debe pasar de 200 a 401.

Integración con el panel: ``attempt_statuses`` y ``format_timeline``
devuelven los códigos para pintar la terminal del atacante en vivo
(``200 → 401``) sin que el panel tenga que parsear stdout.
"""

from __future__ import annotations

import argparse
import os
from typing import Any

import httpx

ALLOWED_HOSTS = {"127.0.0.1", "localhost", "cantina-demo.bendrix.test"}
PAYLOAD = {"model": "muse-spark-1.3", "messages": [{"role": "user", "content": "ping de prueba"}]}


def assert_allowed(url: str) -> str:
    host = httpx.URL(url).host
    if host not in ALLOWED_HOSTS:
        raise SystemExit(f"host no permitido fuera del sandbox: {host!r}")
    return url


def format_timeline(statuses: list[int]) -> str:
    """``[200, 401, 401]`` -> ``"200 → 401 → 401"`` para el panel."""
    return " → ".join(str(s) for s in statuses)


def attempt_statuses(client_or_url: Any, token: str, *, attempts: int = 1) -> list[int]:
    """Codes HTTP de reintentar con el token robado. Acepta TestClient o URL."""
    statuses: list[int] = []
    if hasattr(client_or_url, "post"):
        client = client_or_url
        for _ in range(attempts):
            resp = client.post(
                "/v1/chat/completions",
                json=PAYLOAD,
                headers={"Authorization": f"Bearer {token}"},
            )
            statuses.append(resp.status_code)
        return statuses
    url = assert_allowed(str(client_or_url).rstrip("/") + "/v1/chat/completions")
    for _ in range(attempts):
        try:
            resp = httpx.post(
                url, json=PAYLOAD, headers={"Authorization": f"Bearer {token}"}, timeout=5
            )
            statuses.append(resp.status_code)
        except httpx.HTTPError:
            statuses.append(0)
    return statuses


def probe(base_url: str, token: str) -> int:
    """Un intento contra el gateway propio; 0 si no responde."""
    return attempt_statuses(base_url, token, attempts=1)[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--base-url", default=os.environ.get("SHIELD_GATEWAY_URL", "http://127.0.0.1:8000")
    )
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument(
        "--token", default=os.environ.get("SHIELD_TOKEN_CREW_BODEGA", "shd_crew-bodega_demo")
    )
    a = ap.parse_args()
    statuses = attempt_statuses(a.base_url, a.token, attempts=a.attempts)
    for i, status in enumerate(statuses):
        label = f"HTTP {status}" if status else "sin respuesta del gateway propio"
        print(f"intento {i + 1}: {label}")
    if statuses:
        print(format_timeline(statuses))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
