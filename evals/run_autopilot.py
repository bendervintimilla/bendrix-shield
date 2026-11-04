"""Eval M10 (SIMULACIÓN): compara sin wAIrrior / suspender-todo / contención fina.

Uso: ``uv run python evals/run_autopilot.py`` (sin red ni créditos).
Escribe ``evals/recorded/autopilot-bench.json`` y ``evals/autopilot/REPORT.md``.
Las operaciones legítimas de lectura siguen en modo solo-lectura; las de
escritura solo se pausan en las apps congeladas por el circuit breaker.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shield.autopilot import ContainmentEngine, SecurityEvent, run_pipeline  # noqa: E402

ROOT = Path(__file__).parent
SCENARIOS = ROOT / "autopilot" / "scenarios.json"
BENCH = ROOT / "recorded" / "autopilot-bench.json"
REPORT = ROOT / "autopilot" / "REPORT.md"


def _events(raw: list[dict]) -> list[SecurityEvent]:
    return [SecurityEvent.from_dict({k: v for k, v in item.items() if k != "label"})
            for item in raw]


def evaluate(scenario: dict) -> dict:
    baseline = _events(scenario.get("baseline") or [])
    raw = scenario.get("events") or []
    events = _events(raw)
    labels = {event.event_id: item.get("label")
              for event, item in zip(events, raw, strict=True)}
    engine = ContainmentEngine()
    incident, result = run_pipeline(events, baseline, engine=engine)
    blocked = engine.blocked_actions | engine.held_payments
    malicious = [e for e in events if labels[e.event_id] == "malicious"]
    legit = [e for e in events if labels[e.event_id] == "legit"]
    w_malicious_blocked = sum(1 for e in malicious if e.event_id in blocked)
    # Con circuit breaker la escritura legítima se pausa; la lectura continúa.
    w_legit_write_ok = 0 if result.circuit_breaker else sum(
        1 for e in legit if e.event_id not in blocked)
    legit_write_total = int(scenario.get("legitimate_write_ops") or 0)
    legit_read_total = int(scenario.get("legitimate_read_ops") or 0)
    return {
        "id": scenario["id"], "title": scenario["title"], "simulated": True,
        "severity": incident.severity, "correlated": incident.correlated,
        "circuit_breaker": result.circuit_breaker,
        "findings": [f["kind"] for f in incident.to_dict()["findings"]],
        "detect_to_contain_ms": round(result.detect_to_contain_ms, 3),
        "measures": [m["kind"] for m in result.to_dict()["measures"]],
        "pending_owner": result.pending_owner,
        "notice_en": result.notice_en,
        "comparison": {
            "no_shield": {"malicious_succeed": len(malicious),
                          "legitimate_write_ok": legit_write_total,
                          "legitimate_read_ok": legit_read_total},
            "suspend_all_arkea_style": {"malicious_succeed": 0,
                                        "legitimate_write_ok": 0,
                                        "legitimate_read_ok": 0},
            "wairrior_fine_containment": {
                "malicious_blocked": w_malicious_blocked,
                "malicious_succeed": len(malicious) - w_malicious_blocked,
                "legitimate_events_ok": w_legit_write_ok,
                "legitimate_write_ok": 0 if result.circuit_breaker else legit_write_total,
                "legitimate_read_ok": legit_read_total,
                "writes_paused_by_circuit_breaker": bool(result.circuit_breaker),
            },
        },
    }


def main() -> int:
    data = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    results = [evaluate(s) for s in data["scenarios"]]
    bench = {"simulated": True,
             "label": "SIMULACIÓN — sin datos reales, tiempos locales en ms",
             "sources": data.get("sources"), "scenarios": results}
    BENCH.parent.mkdir(parents=True, exist_ok=True)
    BENCH.write_text(json.dumps(bench, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# Autopilot bench — SIMULACIÓN (M10)", "",
             "Escenarios basados en los ataques reales citados en `ORDENES.md`. "
             "Nada de esto es una medición sobre clientes reales.", "",
             "| Escenario | Severidad | Breaker | Detección→contención (ms, local) | "
             "Maliciosas que pasan sin escudo | Maliciosas bloqueadas wAIrrior | "
             "Escrituras legítimas OK (suspender-todo) | Escrituras legítimas OK (wAIrrior) |",
             "|---|---|---|---|---|---|---|---|"]
    for r in results:
        c = r["comparison"]
        lines.append(
            f"| {r['id']} | {r['severity']} | {r['circuit_breaker']} | "
            f"{r['detect_to_contain_ms']} | {c['no_shield']['malicious_succeed']} | "
            f"{c['wairrior_fine_containment']['malicious_blocked']} | "
            f"{c['suspend_all_arkea_style']['legitimate_write_ok']} | "
            f"{c['wairrior_fine_containment']['legitimate_write_ok']} |")
    lines += ["", "Lectura: suspender todo (patrón Arkéa) frena el ataque pero también "
              "todas las operaciones legítimas. wAIrrior contiene por actor/app y solo "
              "pausa escrituras cuando salta el circuit breaker (≥2 apps o crítico); "
              "las lecturas siguen y cada medida tiene undo. Lo irreversible "
              "(pagar, IBAN definitivo) queda para el dueño con segundo factor.", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"OK {len(results)} escenarios -> {BENCH} y {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
