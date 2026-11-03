#!/usr/bin/env python3
"""Sonda red team de la Cantina Demo: batería adversaria contra el gateway PROPIO.

Defensa pura: corre en proceso con un transporte falso (sin red) o, con
``--base-url``, solo contra la allowlist de `sandbox/attacker.py`
(localhost). Jamás apunta fuera. Los casos son sintéticos y viven en
`evals/redteam/cases.json`; la medición es la de `evals/run_redteam.py`.

Uso: ``uv run python sandbox/redteam.py`` (imprime frenados y pases en
silencio; los bypass conocidos se muestran tal cual, no se maquillan).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.run_redteam import run_battery  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Batería red team (solo sandbox propio).")
    ap.parse_args()
    filas = run_battery()
    frenados = sum(1 for f in filas if f["frenado"])
    print(f"red team: frenados {frenados}/{len(filas)}")
    for f in filas:
        marca = "frenado" if f["frenado"] else "PASA EN SILENCIO"
        print(f"  [{marca}] {f['id']} ({f['vector']}): {f['observado']} — {f['detalle']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
