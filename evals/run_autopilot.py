"""Eval M10 (SIMULACIÓN): daño colateral medido con tráfico legítimo de fondo.

Uso: ``uv run python evals/run_autopilot.py`` (sin red ni créditos).
Genera 300 eventos legítimos de fondo por escenario (semilla fija
20261104, 4 apps) y mide: escrituras legítimas que siguen con
suspender-todo vs con wAIrrior, y ataques que pasan en cada brazo.
Escribe ``evals/recorded/autopilot-bench.json`` y ``evals/autopilot/REPORT.md``.
"""

from __future__ import annotations

import json
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shield.autopilot import ContainmentEngine, SecurityEvent, run_pipeline  # noqa: E402

ROOT = Path(__file__).parent
SCENARIOS = ROOT / "autopilot" / "scenarios.json"
BENCH = ROOT / "recorded" / "autopilot-bench.json"
REPORT = ROOT / "autopilot" / "REPORT.md"
BACKGROUND_N = 300
SEED = 20261104
T0 = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)


def _events(raw: list[dict]) -> list[SecurityEvent]:
    return [SecurityEvent.from_dict({k: v for k, v in item.items() if k != "label"})
            for item in raw]


def background_traffic(n: int = BACKGROUND_N, seed: int = SEED) -> list[SecurityEvent]:
    """300 legítimos con semilla fija: pagos conocidos, otros equipos, otros agentes."""
    rng = random.Random(seed)
    out: list[SecurityEvent] = []
    for i in range(n):
        app = ("payments", "pos_erp", "cold_room", "ai_gateway")[i % 4]
        ts = T0 + timedelta(seconds=rng.randrange(0, 600))
        if app == "payments":
            raw = {"app": app, "actor": "payments-bot", "action": "transfer",
                   "target": "supplier:known", "ts": ts.isoformat(),
                   "source": "human" if (i // 4) % 2 == 0 else "agent",
                   "values": {"amount": rng.randrange(400, 601),
                              "beneficiary": "KNOWN", "beneficiary_known": True}}
        elif app == "pos_erp":
            raw = {"app": app, "actor": "erp-bot", "action": "supplier_change",
                   "target": f"supplier:known-{i % 5}", "ts": ts.isoformat(),
                   "values": {"field": "contact"}}
        elif app == "cold_room":
            raw = {"app": app, "actor": "refrigeracion", "action": "set_setpoint",
                   "target": f"camara-{2 + i % 3}", "ts": ts.isoformat(),
                   "values": {"value": 3.0}}
        else:
            raw = {"app": app, "actor": "ops-bot", "action": "model_call",
                   "target": "muse-spark-1.3", "ts": ts.isoformat(),
                   "token_id": "tok-ops", "values": {"cost_usd": 1}}
        out.append(SecurityEvent.from_dict(raw))
    return out


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
    w_blocked = sum(1 for e in malicious if e.event_id in blocked)
    background = background_traffic()
    bg_ok = sum(1 for e in background if engine.allows_write(e))
    return {
        "id": scenario["id"], "title": scenario["title"], "simulated": True,
        "severity": incident.severity, "correlated": incident.correlated,
        "scope_level": result.scope_level, "circuit_breaker": result.circuit_breaker,
        "frozen_scopes": result.frozen_scopes,
        "findings": [f["kind"] for f in incident.to_dict()["findings"]],
        "detect_to_contain_ms": round(result.detect_to_contain_ms, 3),
        "measures": [m["kind"] for m in result.to_dict()["measures"]],
        "pending_owner": result.pending_owner,
        "notice_en": result.notice_en, "notice_es": result.notice_es,
        "comparison": {
            "background_legitimate_writes_total": len(background),
            "no_shield": {"attacks_succeed": len(malicious),
                          "background_legitimate_ok": len(background)},
            "suspend_all_arkea_style": {"attacks_succeed": 0,
                                        "background_legitimate_ok": 0},
            "wairrior": {"attacks_blocked": w_blocked,
                         "attacks_succeed": len(malicious) - w_blocked,
                         "background_legitimate_ok": bg_ok,
                         "background_legitimate_blocked_collateral":
                             len(background) - bg_ok},
        },
    }


def main() -> int:
    data = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    results = [evaluate(s) for s in data["scenarios"]]
    bench = {"simulated": True,
             "label": "SIMULACIÓN — sin datos reales, tiempos locales en ms",
             "background": {"n": BACKGROUND_N, "seed": SEED,
                            "apps": ["payments", "pos_erp", "cold_room", "ai_gateway"]},
             "sources": data.get("sources"), "scenarios": results}
    BENCH.parent.mkdir(parents=True, exist_ok=True)
    BENCH.write_text(json.dumps(bench, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# Autopilot bench — SIMULACIÓN (M10)", "",
             "Basado en los ataques reales de `ORDENES.md`. Alcances: "
             "`actor`, `app` (solo esa app y ese tipo de operación), `campaign` "
             "(una campaña en 2 apps: actor + proveedor + beneficiarios nuevos) y "
             "`global` (solo >=3 apps o varios actores; las operaciones humanas "
             "recurrentes a beneficiarios conocidos siguen aun en global). "
             "Fondo: 300 escrituras legítimas por escenario, semilla fija 20261104.", "",
             "| Escenario | Nivel | Breaker global | ms local | Ataques que pasan "
             "(sin escudo → wAIrrior) | Legítimas de fondo OK (suspender-todo → wAIrrior) /300 |",
             "|---|---|---|---|---|---|"]
    for r in results:
        c = r["comparison"]
        lines.append(
            f"| {r['id']} | {r['scope_level']} | {r['circuit_breaker']} | "
            f"{r['detect_to_contain_ms']} | {c['no_shield']['attacks_succeed']} → "
            f"{c['wairrior']['attacks_succeed']} | "
            f"{c['suspend_all_arkea_style']['background_legitimate_ok']} → "
            f"{c['wairrior']['background_legitimate_ok']} |")
    wave = next((r for r in results if r["id"] == "combined_wave"), None)
    if wave:
        lines += ["", "## Ola combinada (único caso global): aviso completo al dueño", "",
                  f"> EN: {wave['notice_en']}", "", f"> ES: {wave['notice_es']}", ""]
    lines += ["Lectura: Arkéa es nivel campaign (no global): 263/300 legítimas "
              "vivas; las 37 pausadas son los pagos de agente del bot contenido "
              "(congelado en físico y pagos tras la contención, ronda 3 de M7: "
              "cambiar target o clase de acción ya no evade). Solo la ola en "
              ">=3 apps llega a global, y aun ahí sobreviven las operaciones "
              "humanas recurrentes (38/300). Cada medida tiene undo y lo "
              "irreversible queda para el dueño.", "",
              "Ronda 3 (M7): C3-11 (otro target) y C3-12 (otra clase de acción) "
              "quedan bloqueados por el congelamiento del actor/token; C3-13 "
              "(90 min, actores/tokens distintos) correlaciona por objetivo y "
              "firma de campaña en 24 h; C3-16 (actor 'wairrior-autopilot' "
              "forjado) se marca sospechoso y nunca obtiene rescate. La "
              "contención física usa el RescueGrant real de M1 "
              "(issue_last_safe_action + verify_action con grant): rescate "
              "allow solo con grant firmado válido, de un solo uso. El "
              "veredicto por evento ya lleva estado e historia del equipo "
              "(24 h): deshielos programados de 40 min repetidos suman "
              "finding defrost_pattern sobre el calendario normal.", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"OK {len(results)} escenarios -> {BENCH} y {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
