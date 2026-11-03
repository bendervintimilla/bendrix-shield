"""Ejemplo de cadena de frío: corre el escenario replay y lo imprime.

Uso: ``uv run python examples/cold-chain/run.py`` (sin red ni créditos).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crew.refrigeracion.scenario import run_scenario  # noqa: E402

if __name__ == "__main__":
    result = run_scenario()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
