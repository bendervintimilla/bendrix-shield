"""Mide tiempo y costo de Spark por documento sobre el held-out v2 congelado.

Corre solo si se pide: ``uv run python evals/run_spark_latency.py``. Tope USD 0.50.
Solo mide; no cambia set, reglas ni prompt. Escribe un JSON nuevo por fecha.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.run_heldout2_spark import CountingClient, _is_failed, doc_of, load_cases  # noqa: E402
from shield.policy.spark import make_spark_classifier  # noqa: E402

CAP_USD = 0.50
OUT = Path(__file__).parent / "recorded" / f"spark-latency-{date.today().isoformat()}.json"


def main() -> int:
    client = CountingClient()
    classifier = make_spark_classifier(client)
    rows = []
    try:
        for case in load_cases():
            if client.cost_usd >= CAP_USD:
                break
            doc = doc_of(case)
            before = client.cost_usd
            start = time.perf_counter()
            decision = classifier(
                agent="compras",
                tool=str(case.get("tool", "read_invoice")),
                args=dict(case.get("args") or {}),
                sources_text=doc.text,
            )
            rows.append(
                {
                    "id": case.get("id"),
                    "label": case.get("label"),
                    "seconds": round(time.perf_counter() - start, 3),
                    "cost_usd": round(client.cost_usd - before, 6),
                    "decision": decision.decision.value,
                    "failed": _is_failed(decision),
                    "response_id": client.last_response_id,
                }
            )
    finally:
        client.close()
    secs = sorted(r["seconds"] for r in rows)
    summary = {
        "date": date.today().isoformat(),
        "model": "muse-spark-1.3",
        "calls": len(rows),
        "failed": sum(r["failed"] for r in rows),
        "total_cost_usd": round(client.cost_usd, 6),
        "cost_per_doc_usd": round(client.cost_usd / max(len(rows), 1), 6),
        "seconds_p50": statistics.median(secs) if secs else None,
        "seconds_p90": secs[int(len(secs) * 0.9)] if secs else None,
        "seconds_max": secs[-1] if secs else None,
        "rows": rows,
    }
    OUT.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
