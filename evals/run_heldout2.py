"""Eval held-out v2 de H11: set fresco y ciego a las reglas (evals/heldout2/).

Generado por una sesión fresca sin leer `shield/policy/` (ver `gen_heldout2.py`) y
congelado antes de medir. **Esta es la cifra principal desde H11**; la de
`evals/heldout/` queda como histórica porque H10 ya ajustó reglas con ella.
No se ajusta ninguna regla con este set. Uso: ``uv run python evals/run_heldout2.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import evals.run_heldout as _v1  # noqa: E402
from evals._sections import write_section  # noqa: E402

_v1.HELDOUT_DIR = Path(__file__).parent / "heldout2"
START, END = "<!-- H11:heldout2:start -->", "<!-- H11:heldout2:end -->"


def main() -> int:
    m = _v1.evaluate()
    recall = m["blocked"] / m["poisoned"] if m["poisoned"] else 0.0
    caught = m["blocked"] + m["asked"]
    section = (
        "## Eval held-out v2 (cifra principal, ciega a las reglas) — H11\n\n"
        "Set fresco generado por una sesión fresca sin leer "
        "`shield/policy/` ni las reglas del gate, solo el formato de "
        "`evals/heldout/`. Congelado en `evals/heldout2/` con "
        "`evals/gen_heldout2.py` antes de medir; no se ajustó ninguna "
        "regla con él.\n\n"
        f"- Envenenados: bloqueados {m['blocked']}/{m['poisoned']} "
        f"(recall de bloqueo {recall:.0%}); escalados a `ask_owner`: "
        f"{m['asked']}; frenados en total (block+ask_owner): {caught}/{m['poisoned']}; "
        f"permitidos en silencio: {m['missed']}.\n"
        f"- Cambios legítimos formales en `ask_owner`: {m['legit_ok']}/{m['legit']} "
        f"(bloqueados por error: {m['legit_blocked']}, en silencio: {m['legit_allowed']}).\n"
        f"- Lecturas limpias permitidas: {m['reads_ok']}/{m['reads']}.\n"
        f"- Escrituras sensibles envenenadas en silencio: {m['silent_write_allow']}; "
        f"permitidas en silencio en total: {m['missed']}.\n"
        "- Costo en créditos: USD 0 (sin llamadas a modelos).\n\n"
        "| caso | etiqueta | técnica | decisión | razón |\n|---|---|---|---|---|\n"
        + "\n".join(m["rows"])
        + "\n"
    )
    write_section(START, END, section)
    print(
        f"held-out v2 (PRINCIPAL): bloqueo {m['blocked']}/{m['poisoned']}, "
        f"ask_owner {m['asked']}, en silencio {m['missed']}, "
        f"legítimos {m['legit_ok']}/{m['legit']}, lecturas {m['reads_ok']}/{m['reads']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
