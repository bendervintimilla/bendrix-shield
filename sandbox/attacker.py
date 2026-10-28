#!/usr/bin/env python3
"""Atacante de la Cantina Demo: reusa un token de PRUEBA contra el gateway PROPIO.

Jamás apunta fuera de allowlist.yaml (SPEC §2.2, defensa pura). Sin red real en
tests: la URL por defecto es localhost y los tests usan un transporte falso.
Uso: SHIELD_TOKEN_CREW_BODEGA=<token-demo> python sandbox/attacker.py --attempts 3
Tras rotar el token en el panel, el mismo comando debe pasar de 200 a 401.
"""
from __future__ import annotations
import argparse, os, sys
import httpx

ALLOWED_HOSTS = {"127.0.0.1", "localhost", "cantina-demo.bendrix.test"}

def assert_allowed(url: str) -> str:
    host = httpx.URL(url).host
    if host not in ALLOWED_HOSTS:
        raise SystemExit(f"host no permitido fuera del sandbox: {host!r}")
    return url

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.environ.get("SHIELD_GATEWAY_URL", "http://127.0.0.1:8000"))
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--token", default=os.environ.get("SHIELD_TOKEN_CREW_BODEGA", "shd_crew-bodega_demo"))
    a = ap.parse_args()
    url = assert_allowed(a.base_url.rstrip("/") + "/v1/chat/completions")
    for i in range(a.attempts):
        try:
            r = httpx.post(url, json={"model": "muse-spark-1.3", "messages": [{"role": "user", "content": "ping de prueba"}]}, headers={"Authorization": f"Bearer {a.token}"}, timeout=5)
            print(f"intento {i+1}: HTTP {r.status_code}")
        except httpx.HTTPError as e:
            print(f"intento {i+1}: sin respuesta del gateway propio ({type(e).__name__})")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
