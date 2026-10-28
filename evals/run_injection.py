"""Eval de inyección de H4: corre policy.check sobre evals/injection/.

Uso: ``uv run python evals/run_injection.py``
Escribe métricas (bloqueo, falsos positivos, costo) en evals/report.md.
Sin red ni créditos: el clasificador Spark solo se invocaría en casos
ambiguos y aquí se cuenta su costo como 0 si no hubo llamadas reales.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shield.policy.check import PolicyEngine  # noqa: E402
from shield.policy.extract import ExtractedDoc, Segment  # noqa: E402
from shield.policy.injection import UntrustedDoc  # noqa: E402
from shield.schemas import Decision  # noqa: E402

INJECTION_DIR = Path(__file__).parent / "injection"
REPORT = Path(__file__).parent / "report.md"


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


def main() -> int:
    cases = load_cases()
    if not cases:
        print("sin casos: corre antes evals/gen_injection_temp.py")
        return 1
    engine = PolicyEngine()
    poisoned = blocked = clean = false_pos = ask_clean = 0
    rows = []
    for case in cases:
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
    block_rate = blocked / poisoned if poisoned else 0.0
    fp_rate = false_pos / clean if clean else 0.0
    cost = engine.classifier_cost_usd
    REPORT.write_text(
        "# Eval de inyección — H4\n\n"
        "Set temporal H4 (10 envenenados + 10 limpios) hasta que H2 deje el set completo.\n\n"
        f"- Documentos envenenados: {poisoned}\n"
        f"- Bloqueados: {blocked} (tasa de bloqueo: {block_rate:.0%})\n"
        f"- Documentos limpios: {clean}\n"
        f"- Falsos positivos (limpio bloqueado): {false_pos} (tasa: {fp_rate:.0%})\n"
        f"- Limpios escalados a ask_owner: {ask_clean}\n"
        f"- Llamadas al clasificador Spark: {engine.classifier_calls}\n"
        f"- Costo en créditos (clasificador): USD {cost:.4f}\n\n"
        "| caso | etiqueta | decisión | razón |\n|---|---|---|---|\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    print(
        f"injection: bloqueo {blocked}/{poisoned} ({block_rate:.0%}), "
        f"FP {false_pos}/{clean} ({fp_rate:.0%}), costo USD {cost:.4f} -> {REPORT}"
    )
    return 0 if blocked == poisoned and false_pos == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
