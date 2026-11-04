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
    accepted: list[Any] = []
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
