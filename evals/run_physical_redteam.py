"""Runner del red team fisico (M7): intenta romper gate.verify_action.

Uso: uv run python evals/run_physical_redteam.py [--json]

Determinista, sin red. Lee evals/physical/redteam.json (congelado) y, por caso:
1. Evalua cada paso con verify_action usando el history segun history_mode.
2. Calcula la verdad terreno simulando TODAS las acciones del caso a 720 min
   desde el estado real (true_state si el caso lo trae; si no, el inicial).
3. Clasifica: BYPASS / HELD / STOPPED / INEFFECTIVE (ver redteam.json).

Si M1 aun no publico thermal/gate, reporta PENDING_M1 y sale con codigo 2.
Lo simulado se rotula simulated; ningun valor es medicion real.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

CASES_PATH = Path(__file__).parent / "physical" / "redteam.json"


def _load_gate() -> tuple[Any, Any, Any] | None:
    """Importa M1; None si todavia no existe."""
    try:
        from shield.physics import gate, thermal
        from shield.physics.contract import ColdRoomParams, ProposedAction, RoomState
    except ImportError:
        return None
    return (gate, thermal, (ColdRoomParams, ProposedAction, RoomState))


def _state(contract: Any, base: dict[str, Any], override: dict[str, Any] | None) -> Any:
    """Construye RoomState desde dicts del JSON."""
    _, _, (_, _, room_state) = contract
    data = dict(base)
    if override:
        data.update(override)
    allowed = set(room_state.__dataclass_fields__)
    return room_state(**{k: v for k, v in data.items() if k in allowed})


def _action(contract: Any, raw: dict[str, Any]) -> Any:
    """Construye ProposedAction desde un dict del JSON."""
    _, _, (_, proposed, _) = contract
    allowed = set(proposed.__dataclass_fields__)
    return proposed(**{k: v for k, v in raw.items() if k in allowed})


def _breach(contract: Any, params: Any, state: Any, actions: list[Any], horizon: float) -> dict:
    """Verdad terreno: simula a horizonte largo y mide ruptura de envolvente."""
    gate_mod, thermal, _ = contract
    del gate_mod
    traj = thermal.simulate(params, state, actions, horizon_min=horizon)
    dt_min = (traj.t_min[1] - traj.t_min[0]) if len(traj.t_min) > 1 else 0.0
    above = sum(dt_min for p in traj.product_c if p > params.safe_max_c)
    below = any(p < params.safe_min_c for p in traj.product_c)
    return {
        "breach": bool(above > params.max_minutes_above or below),
        "minutes_above": round(above, 2),
        "peak_product_c": round(max(traj.product_c), 3) if traj.product_c else None,
        "min_product_c": round(min(traj.product_c), 3) if traj.product_c else None,
        "below_safe_min": below,
    }


def run_case(contract: Any, params: Any, case: dict[str, Any], defaults: dict[str, Any],
             gate_horizon: float, truth_horizon: float) -> dict[str, Any]:
    """Evalua un caso congelado contra el gate y la verdad terreno."""
    gate_mod, _, _ = contract
    mode = case.get("history_mode", "carry")
    initial = case.get("true_state") or case.get("initial_state") or defaults
    if case.get("ground_truth_from_first_step_state") and case["steps"]:
        initial = {**defaults, **(case["steps"][0].get("state") or {})}
    decisions: list[str] = []
    accepted: list[Any] = [_action(contract, h) for h in case.get("history_seed", [])]
    all_actions: list[Any] = []
    for step in case["steps"]:
        action = _action(contract, step["action"])
        all_actions.append(action)
        state = _state(contract, case.get("initial_state") or defaults, step.get("state"))
        if mode == "carry":
            history = list(accepted)
        elif mode == "explicit":
            history = [_action(contract, h) for h in step.get("history", [])]
        else:
            history = []
        verdict = gate_mod.verify_action(
            params, state, action, history=history, horizon_min=gate_horizon
        )
        decisions.append(verdict.decision)
        if verdict.decision != "block":
            accepted.append(action)
    truth_state = _state(contract, defaults, initial)
    truth = _breach(contract, params, truth_state, all_actions, truth_horizon)
    # Solo lo no bloqueado llegaria a ejecutarse (ask_owner si el dueno acepta):
    # si eso ya rompe, el block llego tarde.
    truth_executed = _breach(contract, params, truth_state, accepted, truth_horizon)
    if "block" in decisions:
        result = "STOPPED"
    elif truth["breach"] and "ask_owner" in decisions:
        result = "HELD"
    elif truth["breach"]:
        result = "BYPASS"
    else:
        result = "INEFFECTIVE"
    return {
        "id": case["id"],
        "category": case["category"],
        "title": case["title"],
        "is_control": bool(case.get("is_control")),
        "decisions": decisions,
        "result": result,
        "ground_truth": truth,
        "ground_truth_executed_only": truth_executed,
        "damage_before_block": bool("block" in decisions and truth_executed["breach"]),
    }


def _gen_history(contract: Any, params: Any, gen: dict[str, Any]) -> tuple[list[Any], list[float]]:
    """Genera (estados, reportado) deterministicos para casos de pipeline."""
    _, thermal, (_, _, room_state) = contract
    from shield.physics.contract import ProposedAction

    minutes = int(gen.get("minutes", 120))
    mode = gen.get("compressor", "thermostat")
    actions = []
    if mode == "off":
        actions = [ProposedAction(kind="compressor_off", duration_min=float(minutes))]
    base = _state(contract, {"air_c": 3.0, "product_c": 3.0, "product_kg": 200.0,
                             "setpoint_c": 3.0, "compressor_on": False}, None)
    traj = thermal.simulate(params, base, actions, horizon_min=float(minutes))
    states, reported = [], []
    kind = gen.get("kind", "truth")
    for i in range(minutes):
        idx = min(i * 2, len(traj.t_min) - 1)
        air, prod = traj.air_c[idx], traj.product_c[idx]
        if kind == "fake_flat":
            air = prod = float(gen.get("reported_c", 3.0))
            reported.append(float(gen.get("reported_c", 3.0)))
        elif kind == "biased":
            bias = float(gen.get("bias_c", 0.0))
            air, prod = air + bias, prod + bias
            reported.append(air)
        else:
            reported.append(air)
        states.append(room_state(
            t_min=float(i), air_c=air, product_c=prod, product_kg=200.0,
            setpoint_c=3.0, compressor_on=bool(traj.compressor_on[idx]),
            door_open=False, minutes_above_so_far=0.0))
    return states, reported


def run_chain_case(contract: Any, params: Any, case: dict[str, Any],
                   defaults: dict[str, Any]) -> dict[str, Any]:
    """Corre un caso de ronda 3 segun su nivel (pipeline/gate/autopilot)."""
    level = case.get("level", "gate")
    out: dict[str, Any] = {"id": case["id"], "level": level,
                           "category": case["category"], "title": case["title"],
                           "is_control": bool(case.get("is_control"))}
    if level == "pipeline":
        from shield.physics.pipeline import verify_before_actuate

        states, reported = _gen_history(contract, params, case["history_gen"])
        action = _action(contract, case["action"])
        verdict = verify_before_actuate(params, states, reported, action)
        pipe = verdict.evidence.get("pipeline", {})
        out["decisions"] = [verdict.decision]
        out["sensor_spoofed"] = pipe.get("sensor_spoofed")
        out["result"] = {"block": "STOPPED", "ask_owner": "HELD"}.get(
            verdict.decision, "BYPASS")
    elif level == "autopilot":
        from datetime import UTC, datetime, timedelta

        from shield.autopilot.events import SecurityEvent
        from shield.autopilot.respond import ContainmentEngine, run_pipeline

        base_ts = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)

        def build(raw: dict[str, Any]) -> Any:
            return SecurityEvent(
                app=raw["app"], actor=raw["actor"], action=raw["action"],
                target=raw.get("target", ""), values=dict(raw.get("values", {})),
                source=raw.get("source", "agent"),
                ts=base_ts + timedelta(minutes=float(raw.get("offset_min", 0))),
                token_id=raw.get("token_id"))

        events = [build(e) for e in case["events"]]
        engine = ContainmentEngine()
        incident, result = run_pipeline(events, engine=engine)
        out["correlated"] = incident.correlated
        out["severity"] = incident.severity
        out["scope_level"] = result.scope_level
        out["circuit_breaker"] = result.circuit_breaker
        out["findings"] = [f.kind for f in incident.findings]
        if case.get("retry_event"):
            retry = build(case["retry_event"])
            out["retry_allowed"] = engine.allows_write(retry)
            out["result"] = "BYPASS" if out["retry_allowed"] else "STOPPED"
        elif out["is_control"]:
            out["result"] = "CORRELATED" if incident.correlated else "EVADED"
        else:
            out["result"] = "CORRELATED" if incident.correlated else "EVADED"
    else:
        gate_case = {**case, "history_mode": case.get("history_mode", "carry")}
        r = run_case(contract, params, gate_case, defaults, 240.0, 720.0)
        out.update({"decisions": r["decisions"], "result": r["result"]})
    return out


def main() -> int:
    """Corre todos los casos y resume; --json emite el detalle completo."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emitir JSON completo")
    parser.add_argument("--cases", type=Path, default=CASES_PATH,
                        help="archivo de casos (default: redteam.json congelado)")
    args = parser.parse_args()
    data = json.loads(args.cases.read_text(encoding="utf-8"))
    loaded = _load_gate()
    if loaded is None:
        print("PENDING_M1: shield.physics.gate/thermal aun no estan en esta rama.")
        print(f"Casos congelados listos para correr: {len(data['cases'])}")
        return 2
    gate_mod, thermal, classes = loaded
    del gate_mod, thermal
    cold_params, _, _ = classes
    params = cold_params(**data.get("params", {}))
    contract = loaded
    if "chain_cases" in data:
        chain = [run_chain_case(contract, params, c, data["default_state"])
                 for c in data["chain_cases"]]
        counts: dict[str, int] = {}
        for r in chain:
            counts[r["result"]] = counts.get(r["result"], 0) + 1
        if args.json:
            print(json.dumps({"summary": {"label": "simulated",
                                          "cases_file": args.cases.name,
                                          "counts": counts},
                              "results": chain}, ensure_ascii=False, indent=2))
        else:
            for r in chain:
                extra = {k: r[k] for k in ("sensor_spoofed", "correlated", "severity",
                                           "scope_level", "retry_allowed", "decisions")
                         if k in r}
                print(f"{r['id']} [{r['level']}/{r['category']}] {r['result']}: {extra}")
            print(json.dumps({"label": "simulated", "counts": counts},
                             ensure_ascii=False))
        return 0
    results = [
        run_case(contract, params, case, data["default_state"],
                 float(data["gate_horizon_min"]), float(data["ground_truth_horizon_min"]))
        for case in data["cases"]
    ]
    attacks = [r for r in results if not r["is_control"]]
    controls = [r for r in results if r["is_control"]]
    summary = {
        "label": "simulated",
        "cases_file": args.cases.name,
        "attacks_total": len(attacks),
        "bypass": sum(r["result"] == "BYPASS" for r in attacks),
        "held": sum(r["result"] == "HELD" for r in attacks),
        "stopped": sum(r["result"] == "STOPPED" for r in attacks),
        "ineffective": sum(r["result"] == "INEFFECTIVE" for r in attacks),
        "controls_blocked": sum(
            "block" in r["decisions"] for r in controls
        ),
    }
    if args.json:
        print(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2))
    else:
        for r in results:
            truth = r["ground_truth"]
            print(f"{r['id']} [{r['category']}] {r['result']}: "
                  f"decisions={','.join(r['decisions'])} peak={truth['peak_product_c']} "
                  f"min_above={truth['minutes_above']}")
        print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
