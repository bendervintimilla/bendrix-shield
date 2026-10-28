"""Eval held-out de H9: set duro y ciego a las reglas (evals/heldout/).

Uso: ``uv run python evals/run_heldout.py`` (sin red ni créditos).
Mide el mismo PolicyEngine de H4. Los limpios que cambian la cuenta con
aviso formal valen como acierto solo si caen en ``ask_owner`` (ni bloqueo
ni permiso silencioso). Escribe su sección sin tocar las demás.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals._sections import write_section  # noqa: E402
from shield.policy.check import PolicyEngine  # noqa: E402
from shield.policy.extract import ExtractedDoc, Segment  # noqa: E402
from shield.policy.injection import UntrustedDoc  # noqa: E402
from shield.schemas import Decision  # noqa: E402

HELDOUT_DIR = Path(__file__).parent / "heldout"
START, END = "<!-- H9:heldout:start -->", "<!-- H9:heldout:end -->"


def load_cases() -> list[dict]:
    cases = []
    for path in sorted(HELDOUT_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_file"] = path.name
        cases.append(data)
    return cases


def doc_of(case: dict) -> UntrustedDoc:
    segments = [
        Segment(str(s.get("location", "body")), str(s.get("text", "")))
        for s in case.get("segments", [])
    ]
    return UntrustedDoc(
        doc_id=str(case.get("id", case["_file"])),
        extracted=ExtractedDoc(doc_id=str(case.get("id")), segments=segments),
    )


def evaluate() -> dict:
    engine = PolicyEngine()
    rows = []
    poisoned = blocked = missed = asked = 0
    legit = legit_ok = legit_blocked = legit_allowed = 0
    reads = reads_ok = 0
    silent_write_allow = 0
    for case in load_cases():
        decision = engine.check(
            "compras",
            str(case.get("tool", "read_invoice")),
            dict(case.get("args") or {}),
            [doc_of(case)],
        )
        value = decision.decision.value
        if case.get("label") == "poisoned":
            poisoned += 1
            blocked += decision.decision is Decision.BLOCK
            asked += decision.decision is Decision.ASK_OWNER
            missed += decision.decision is Decision.ALLOW
        elif case.get("expected") == "ask_owner":
            legit += 1
            legit_ok += decision.decision is Decision.ASK_OWNER
            legit_blocked += decision.decision is Decision.BLOCK
            legit_allowed += decision.decision is Decision.ALLOW
        else:
            reads += 1
            reads_ok += decision.decision is Decision.ALLOW
        if (
            case.get("label") == "poisoned"
            and case.get("tool") != "read_invoice"
            and decision.decision is Decision.ALLOW
        ):
            silent_write_allow += 1
        rows.append(
            f"| {case.get('id')} | {case.get('label')} | {case.get('technique')} "
            f"| {value} | {decision.reason[:56]} |"
        )
    return {
        "poisoned": poisoned,
        "blocked": blocked,
        "asked": asked,
        "missed": missed,
        "legit": legit,
        "legit_ok": legit_ok,
        "legit_blocked": legit_blocked,
        "legit_allowed": legit_allowed,
        "reads": reads,
        "reads_ok": reads_ok,
        "silent_write_allow": silent_write_allow,
        "rows": rows,
    }


def format_section(m: dict) -> str:
    recall = m["blocked"] / m["poisoned"] if m["poisoned"] else 0.0
    return (
        "## Eval held-out (ciego a las reglas) — H9\n\n"
        "Set generado sin consultar los patrones de `shield/policy/` "
        "(paráfrasis ES/EN/PT, órdenes en varias líneas, imagen con ruido "
        "OCR y cartas formales legítimas de cambio de cuenta). Congelado en "
        "`evals/heldout/` con `evals/gen_heldout.py`: no se retoca para "
        "subir la cifra.\n\n"
        f"- Envenenados bloqueados: {m['blocked']}/{m['poisoned']} "
        f"(recall {recall:.0%}); escalados a `ask_owner` (los frena el "
        f"dueño, no pasan en silencio): {m['asked']}; permitidos en "
        f"silencio: {m['missed']}.\n"
        f"- Cambios legítimos con aviso formal en `ask_owner`: "
        f"{m['legit_ok']}/{m['legit']} (bloqueados por error: "
        f"{m['legit_blocked']}, permitidos en silencio: {m['legit_allowed']}).\n"
        f"- Lecturas limpias permitidas: {m['reads_ok']}/{m['reads']}.\n"
        f"- Escrituras sensibles envenenadas permitidas en silencio: "
        f"{m['silent_write_allow']}. H10: ninguna acción, incluida una "
        "lectura que pide revelar un secreto, llave o token, pasa en "
        f"silencio (permitidas en silencio en total: {m['missed']}).\n"
        "- Costo en créditos: USD 0 (sin llamadas a modelos).\n\n"
        "| caso | etiqueta | técnica | decisión | razón |\n|---|---|---|---|---|\n"
        + "\n".join(m["rows"])
    )


def main() -> int:
    metrics = evaluate()
    write_section(START, END, format_section(metrics))
    print(
        f"held-out: bloqueo {metrics['blocked']}/{metrics['poisoned']}, "
        f"ask_owner legítimo {metrics['legit_ok']}/{metrics['legit']}, "
        f"lecturas {metrics['reads_ok']}/{metrics['reads']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
