"""C2490: los bypass que esta ronda cierra siguen frenados en la batería."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.run_redteam import CIERRES_C2490, run_battery  # noqa: E402


def test_bypass_cerrados_en_c2490_quedan_frenados():
    filas = {f["id"]: f for f in run_battery()}
    assert set(CIERRES_C2490) <= set(filas)
    abiertos = [i for i in CIERRES_C2490 if not filas[i]["frenado"]]
    assert abiertos == [], f"bypass que C2490 cerró y volvieron a pasar: {abiertos}"
    assert all(filas[i]["expect"] == "gap" for i in CIERRES_C2490)
