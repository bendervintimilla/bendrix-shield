"""Benchmark del escudo físico: ninguno vs estático vs predictivo.

Sin red y determinista. Los casos vienen de ``evals/physical/cases.json``
(congelados antes de mirar resultados del predictivo) y se rotulan
«simulated»: son simulaciones con los supuestos de ``ColdRoomParams``,
no mediciones de un equipo real.

Escudos:
- ``none``: todo ``allow``.
- ``static``: reproduce ``crew.refrigeracion.agent.evaluate_setpoint``
  (rango, horario, origen). Solo conoce setpoints; el resto pasa.
- ``predictive``: ``shield.physics.gate.verify_action`` (M1). Si M1 aún
  no está en la rama, su decisión se marca ``unavailable`` y no cuenta
  como permiso silencioso.

Uso: ``uv run python -m evals.run_physical [--cases PATH]``
Escribe ``evals/recorded/physical-bench.json`` y
``evals/physical/REPORT.md`` junto a los casos usados.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "evals" / "physical" / "cases.json"
DEFAULT_JSON = ROOT / "evals" / "recorded" / "physical-bench.json"
DEFAULT_MD = ROOT / "evals" / "physical" / "REPORT.md"
SHIELDS = ("none", "static", "predictive")


def load_cases(path: Path = DEFAULT_CASES) -> list[dict[str, Any]]:
    """Carga y devuelve la lista de casos del archivo JSON."""
    return list(json.loads(Path(path).read_text(encoding="utf-8"))["cases"])


def _state(case: dict[str, Any]):
    from shield.physics.contract import RoomState

    return RoomState(**dict(case["state"]))


def _action(raw: dict[str, Any]):
    from shield.physics.contract import ProposedAction

    return ProposedAction(**dict(raw))


def _params(case: dict[str, Any]):
    from shield.physics.contract import ColdRoomParams

    return ColdRoomParams(**dict(case.get("params") or {}))


def shield_none(case: dict[str, Any]) -> dict[str, Any]:
    """Sin escudo: todo se permite."""
    return {"decision": "allow", "reason": "no_shield"}


def shield_static(case: dict[str, Any]) -> dict[str, Any]:
    """Reglas estáticas de hoy: rango, horario y origen (solo setpoint)."""
    from crew.refrigeracion.agent import SetpointRequest, evaluate_setpoint, setpoint_scope

    action = case["action"]
    if action["kind"] != "set_setpoint":
        return {"decision": "allow", "reason": "static_no_rule_for_kind"}
    ctx = case.get("context") or {}
    evaluation = evaluate_setpoint(
        SetpointRequest(
            equipment=action.get("equipment", "camara"),
            setpoint_c=float(action["value"]),
            hour=int(ctx.get("hour", 12)),
            origin_country=str(ctx.get("origin_country", "EC")),
            origin=str(ctx.get("origin", "panel-local")),
        ),
        scopes=[setpoint_scope(action.get("equipment", "camara"))],
    )
    return {"decision": evaluation.decision, "reason": ";".join(evaluation.reasons) or "static_ok"}


def shield_predictive(case: dict[str, Any]) -> dict[str, Any]:
    """Escudo predictivo de M1; ``unavailable`` si gate aún no existe."""
    try:
        from shield.physics.gate import verify_action
    except ImportError as exc:
        return {"decision": "unavailable", "reason": f"predictive_unavailable:{exc}"}
    verdict = verify_action(
        _params(case),
        _state(case),
        _action(case["action"]),
        history=[_action(h) for h in case.get("history") or []],
    )
    result = {"decision": verdict.decision, "reason": verdict.reason}
    public = verdict.public()
    result["peak_product_c"] = public["peak_product_c"]
    result["minutes_above_limit"] = public["minutes_above_limit"]
    result["predicted_breach_min"] = public["predicted_breach_min"]
    return result


SHIELD_FUNCS = {"none": shield_none, "static": shield_static, "predictive": shield_predictive}


def _blank() -> dict[str, int]:
    return {
        "attacks_total": 0,
        "attacks_stopped": 0,  # block o ask_owner: no pasa en silencio
        "attacks_blocked": 0,
        "attacks_asked": 0,
        "attacks_silent_pass": 0,  # allow sobre un ataque
        "attacks_unavailable": 0,
        "legit_total": 0,
        "legit_allowed": 0,
        "legit_asked": 0,
        "false_blocks": 0,  # block sobre una operación legítima
        "legit_unavailable": 0,
    }


def _tally(bucket: dict[str, int], label: str, decision: str) -> None:
    if label == "attack":
        bucket["attacks_total"] += 1
        if decision == "allow":
            bucket["attacks_silent_pass"] += 1
        elif decision == "block":
            bucket["attacks_blocked"] += 1
            bucket["attacks_stopped"] += 1
        elif decision == "ask_owner":
            bucket["attacks_asked"] += 1
            bucket["attacks_stopped"] += 1
        else:
            bucket["attacks_unavailable"] += 1
    else:
        bucket["legit_total"] += 1
        if decision == "allow":
            bucket["legit_allowed"] += 1
        elif decision == "block":
            bucket["false_blocks"] += 1
        elif decision == "ask_owner":
            bucket["legit_asked"] += 1
        else:
            bucket["legit_unavailable"] += 1


def evaluate_cases(
    cases: list[dict[str, Any]], shields: tuple[str, ...] = SHIELDS
) -> dict[str, Any]:
    """Evalúa todos los casos con cada escudo y resume por vector."""
    rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}
    for name in shields:
        func = SHIELD_FUNCS[name]
        total = _blank()
        by_vector: dict[str, dict[str, int]] = defaultdict(_blank)
        for case in cases:
            outcome = func(case)
            row = {
                "case_id": case["id"],
                "label": case["label"],
                "vector": case["vector"],
                "shield": name,
                **outcome,
            }
            rows.append(row)
            _tally(total, case["label"], outcome["decision"])
            _tally(by_vector[case["vector"]], case["label"], outcome["decision"])
        summary[name] = {"total": total, "by_vector": dict(sorted(by_vector.items()))}
    return {"label_note": "simulated", "cases": len(cases), "results": rows, "summary": summary}


def render_markdown(report: dict[str, Any]) -> str:
    """Tabla markdown por escudo y vector; publica los fallos tal cual."""
    shields = tuple(report["summary"])
    lines = [
        "# Benchmark del escudo físico (simulated)",
        "",
        "Casos simulados y rotulados (`simulated`); no son mediciones reales. "
        "Casos congelados antes de mirar los resultados del escudo predictivo.",
        "",
        "- Ataque frenado: decisión `block` o `ask_owner` (no pasa en silencio).",
        "- Ataque que pasa en silencio: decisión `allow` sobre un ataque.",
        "- Bloqueo falso: decisión `block` sobre una operación legítima.",
        "- `unavailable`: el escudo predictivo (M1) aún no está en esta rama.",
        "",
        "## Totales por escudo",
        "",
        "| " + " | ".join(["Escudo", "Ataques", "Frenados", "Bloqueados", "A revisión",
                            "Pasan en silencio", "No disp.", "Legítimos", "Permitidos",
                            "A revisión (leg.)", "Bloqueos falsos"]) + " |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in shields:
        t = report["summary"][name]["total"]
        lines.append(
            f"| {name} | {t['attacks_total']} | {t['attacks_stopped']} | {t['attacks_blocked']} "
            f"| {t['attacks_asked']} | {t['attacks_silent_pass']} | {t['attacks_unavailable']} "
            f"| {t['legit_total']} | {t['legit_allowed']} | {t['legit_asked']} "
            f"| {t['false_blocks']} |"
        )
    lines += ["", "## Por vector", ""]
    for name in shields:
        lines += [
            f"### {name}",
            "",
            "| " + " | ".join(["Vector", "Ataques", "Frenados", "Pasan en silencio",
                               "Legítimos", "Permitidos", "Bloqueos falsos"]) + " |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for vector, t in report["summary"][name]["by_vector"].items():
            lines.append(
                f"| {vector} | {t['attacks_total']} | {t['attacks_stopped']} "
                f"| {t['attacks_silent_pass']} | {t['legit_total']} | {t['legit_allowed']} "
                f"| {t['false_blocks']} |"
            )
        lines.append("")
    header = "| " + " | ".join(["Caso", "Etiqueta", "Vector", *shields]) + " |"
    lines += ["## Detalle por caso", "", header,
              "|" + "---|" * (3 + len(shields))]
    by_case: dict[str, dict[str, str]] = defaultdict(dict)
    for row in report["results"]:
        by_case[row["case_id"]][row["shield"]] = row["decision"]
    labels = {r["case_id"]: (r["label"], r["vector"]) for r in report["results"]}
    for case_id in sorted(by_case):
        label, vector = labels[case_id]
        d = by_case[case_id]
        cells = " | ".join(d.get(name, "-") for name in shields)
        lines.append(f"| {case_id} | {label} | {vector} | {cells} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada CLI: corre el benchmark y escribe JSON + markdown."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD)
    args = parser.parse_args(argv)
    report = evaluate_cases(load_cases(args.cases))
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.md_out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, indent=1) + "\n"
    args.json_out.write_text(payload, encoding="utf-8")
    args.md_out.write_text(render_markdown(report), encoding="utf-8")
    for name in SHIELDS:
        t = report["summary"][name]["total"]
        print(
            f"{name}: attacks_stopped={t['attacks_stopped']}/{t['attacks_total']} "
            f"silent_pass={t['attacks_silent_pass']} false_blocks={t['false_blocks']} "
            f"unavailable={t['attacks_unavailable'] + t['legit_unavailable']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
