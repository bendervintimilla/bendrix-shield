"""Eval de inyección sintética: policy.check sobre evals/injection/ (H2/H4).

Uso: ``uv run python evals/run_injection.py``
Escribe solo su sección marcada en evals/report.md (no pisa a H5/H7/H9).
Sin red ni créditos. Ojo: este set se generó con los mismos patrones que
las reglas, así que su 100 % no es la cifra para el jurado; la cifra
independiente es la del set held-out de H9 (``run_heldout.py``).
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

INJECTION_DIR = Path(__file__).parent / "injection"
START, END = "<!-- H4:injection:start -->", "<!-- H4:injection:end -->"


def load_cases() -> list[dict]:
    cases = []
    for path in sorted(INJECTION_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_file"] = path.name
        cases.append(data)
    return cases


def doc_of(case: dict) -> UntrustedDoc:
    segments = [
        Segment(str(s.get("location", "body")), str(s.get("text", "")))
        for s in case.get("segments", [])
    ]
    if not segments and case.get("text"):
        segments = [Segment("body", str(case["text"]))]
    return UntrustedDoc(
        doc_id=str(case.get("id", case["_file"])),
        extracted=ExtractedDoc(doc_id=str(case.get("id")), segments=segments),
    )


def evaluate() -> dict:
    engine = PolicyEngine()
    poisoned = blocked = clean = false_pos = ask_clean = 0
    rows = []
    for case in load_cases():
        label = case.get("label")
        decision = engine.check(
            "compras",
            str(case.get("tool", "read_invoice")),
            dict(case.get("args") or {}),
            [doc_of(case)],
        )
        is_block = decision.decision is Decision.BLOCK
        if label == "poisoned":
            poisoned += 1
            blocked += is_block
        elif label == "clean":
            clean += 1
            false_pos += is_block
            ask_clean += decision.decision is Decision.ASK_OWNER
        rows.append(
            f"| {case.get('id')} | {label} | {decision.decision.value} | {decision.reason[:60]} |"
        )
    return {
        "poisoned": poisoned,
        "blocked": blocked,
        "clean": clean,
        "false_pos": false_pos,
        "ask_clean": ask_clean,
        "classifier_calls": engine.classifier_calls,
        "cost_usd": engine.classifier_cost_usd,
        "rows": rows,
    }


def format_section(m: dict) -> str:
    block_rate = m["blocked"] / m["poisoned"] if m["poisoned"] else 0.0
    fp_rate = m["false_pos"] / m["clean"] if m["clean"] else 0.0
    return (
        "## Eval de inyección sintética — H4 (set de H2)\n\n"
        "Set de 30 envenenados + 30 limpios generado con los mismos patrones "
        "que las reglas: sirve como regresión, **no** como cifra para el "
        "jurado. La medición independiente está en la sección held-out de H9.\n\n"
        f"- Documentos envenenados: {m['poisoned']}\n"
        f"- Bloqueados: {m['blocked']} (tasa de bloqueo: {block_rate:.0%})\n"
        f"- Documentos limpios: {m['clean']}\n"
        f"- Falsos positivos (limpio bloqueado): {m['false_pos']} (tasa: {fp_rate:.0%})\n"
        f"- Limpios escalados a ask_owner: {m['ask_clean']}\n"
        f"- Llamadas al clasificador Spark: {m['classifier_calls']}\n"
        f"- Costo en créditos (clasificador): USD {m['cost_usd']:.4f}\n\n"
        "| caso | etiqueta | decisión | razón |\n|---|---|---|---|\n" + "\n".join(m["rows"])
    )


def main() -> int:
    metrics = evaluate()
    write_section(START, END, format_section(metrics))
    block_rate = metrics["blocked"] / metrics["poisoned"] if metrics["poisoned"] else 0.0
    fp_rate = metrics["false_pos"] / metrics["clean"] if metrics["clean"] else 0.0
    print(
        f"injection: bloqueo {metrics['blocked']}/{metrics['poisoned']} ({block_rate:.0%}), "
        f"FP {metrics['false_pos']}/{metrics['clean']} ({fp_rate:.0%}), "
        f"costo USD {metrics['cost_usd']:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
