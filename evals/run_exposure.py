"""Eval de exposición de H5: ThreatCard x Asset contra evals/estates/.

Uso: ``uv run python evals/run_exposure.py`` (determinista, sin red).
Con ``--triage`` los candidatos ambiguos pasan por Muse Wonder; sin
créditos quedan marcados needs_wonder y la métrica principal no cambia.
Escribe su sección en evals/report.md sin tocar las de otras sesiones.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shield.exposure import match_all, triage_difficult  # noqa: E402
from shield.schemas import Asset, ThreatCard  # noqa: E402

ROOT = Path(__file__).parent
REPORT = ROOT / "report.md"
START, END = "<!-- H5:exposure:start -->", "<!-- H5:exposure:end -->"
CONFIRMED_THRESHOLD = 0.8


def load_threats() -> list[ThreatCard]:
    return [
        ThreatCard.model_validate(json.loads(p.read_text(encoding="utf-8")))
        for p in sorted((ROOT / "advisories").glob("*.json"))
    ]


def metrics(pairs: set[tuple[str, str]], truth: set[tuple[str, str]]) -> dict[str, float]:
    tp = len(pairs & truth)
    fp = len(pairs - truth)
    fn = len(truth - pairs)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
    }


def write_section(text: str) -> None:
    current = REPORT.read_text(encoding="utf-8") if REPORT.is_file() else "# Evals\n"
    section = f"{START}\n{text}\n{END}"
    if START in current and END in current:
        before, rest = current.split(START, 1)
        _, after = rest.split(END, 1)
        current = before + section + after
    else:
        current = current.rstrip() + "\n\n" + section + "\n"
    REPORT.write_text(current, encoding="utf-8")


def main() -> int:
    threats = load_threats()
    truth: set[tuple[str, str]] = set()
    confirmed: set[tuple[str, str]] = set()
    candidates: set[tuple[str, str]] = set()
    triaged = needs_credits = 0
    cost = 0.0
    for path in sorted((ROOT / "estates").glob("*.json")):
        estate = json.loads(path.read_text(encoding="utf-8"))
        assets = [Asset.model_validate(a) for a in estate.get("assets") or []]
        for expected in estate.get("expected_exposures") or []:
            if expected.get("exposed"):
                truth.add((expected["threat_id"], expected["asset_id"]))
        exposures = match_all(threats, assets)
        if "--triage" in sys.argv:
            result = triage_difficult(threats, assets)
            exposures = result.exposures
            triaged += result.triaged
            needs_credits += int(result.needs_credits)
            cost += result.cost_usd
        for exposure in exposures:
            pair = (exposure.threat_id, exposure.asset_id)
            candidates.add(pair)
            if exposure.confidence >= CONFIRMED_THRESHOLD:
                confirmed.add(pair)
    main_m = metrics(confirmed, truth)
    cand_m = metrics(candidates, truth)
    text = (
        "## Eval de exposición — H5\n\n"
        f"- Pares evaluados contra {len(threats)} avisos y 30 estates sintéticos (H2).\n"
        f"- Confirmadas (confianza >= {CONFIRMED_THRESHOLD}): "
        f"precisión {main_m['precision']:.3f}, recall {main_m['recall']:.3f} "
        f"(TP {main_m['tp']}, FP {main_m['fp']}, FN {main_m['fn']}).\n"
        f"- Incluyendo candidatos para triaje: precisión {cand_m['precision']:.3f}, "
        f"recall {cand_m['recall']:.3f} "
        f"(TP {cand_m['tp']}, FP {cand_m['fp']}, FN {cand_m['fn']}).\n"
        f"- Triaje Wonder: {triaged} candidatos, needs_credits en {needs_credits} estates, "
        f"costo USD {cost:.4f}.\n"
        "- Nota: CVE-2026-109618/109619 traen el mismo rango PHP; el determinista confirma "
        "ambos y el set etiqueta solo uno, lo que baja la precisión sin ser un fallo de rango.\n"
    )
    write_section(text)
    print(
        f"exposure: precision={main_m['precision']:.3f} recall={main_m['recall']:.3f} "
        f"(TP {main_m['tp']} FP {main_m['fp']} FN {main_m['fn']}); "
        f"candidatos precision={cand_m['precision']:.3f} recall={cand_m['recall']:.3f} -> {REPORT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
