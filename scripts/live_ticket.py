"""Imprime una URL de acceso de 10 min para pruebas automáticas del modo en vivo.

El código se lee de LIVE_ACCESS_CODE (o de stdin) y no se imprime nunca.
Uso: gcloud secrets versions access latest --secret=shield-live-access-code \
       | python scripts/live_ticket.py https://<servicio>.run.app
"""

from __future__ import annotations

import os
import sys

from web.live_access import make_ticket


def main() -> int:
    base = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else ""
    code = os.environ.get("LIVE_ACCESS_CODE") or sys.stdin.read().strip()
    if not base or len(code) < 16:
        print("uso: LIVE_ACCESS_CODE=... python scripts/live_ticket.py <url>", file=sys.stderr)
        return 2
    print(f"{base}/live/login?t={make_ticket(code)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
