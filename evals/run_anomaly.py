"""Eval de anomalías de H5 sobre evals/usage/ (H2).

Uso: ``uv run python evals/run_anomaly.py`` (sin red ni créditos).
Baseline: la serie normal de 7 días. Objetivo: la serie de abuso de ~16 h.
Una llamada del abuso es positiva real si trae país nuevo, modelo no usado
o el costo del abuso; las llamadas normales dentro de la serie son negativas.
Escribe su sección en evals/report.md sin tocar las de otras sesiones.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shield.anomaly import detect_anomalies, flagged_logs, load_usage_file  # noqa: E402

ROOT = Path(__file__).parent
REPORT = ROOT / "report.md"
START, END = "<!-- H5:anomaly:start -->", "<!-- H5:anomaly:end -->"


def is_abuse_call(
    call: object,
    baseline_countries: set[str],
    baseline_models: set[str],
    baseline_costs: list[float],
) -> bool:
    median = sorted(baseline_costs)[len(baseline_costs) // 2] if baseline_costs else 0.0
    return bool(
        (call.src_country and call.src_country not in baseline_countries)  # type: ignore[attr-defined]
        or call.model not in baseline_models  # type: ignore[attr-defined]
        or (median > 0 and call.cost_usd > median * 5)  # type: ignore[attr-defined]
    )


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
    normal, _ = load_usage_file(ROOT / "usage/crew-bodega_normal_7d.json")
    abuse, abuse_meta = load_usage_file(ROOT / "usage/crew-bodega_abuse_16h.json")
    findings = detect_anomalies(abuse, normal)
    flagged = flagged_logs(abuse, normal)
    flagged_ids = {id(c) for c in flagged}

    countries = {c.src_country for c in normal if c.src_country}
    models = {c.model for c in normal}
    costs = [c.cost_usd for c in normal]
    tp = fp = fn = 0
    for call in abuse:
        real = is_abuse_call(call, countries, models, costs)
        hit = id(call) in flagged_ids
        tp += int(real and hit)
        fp += int(not real and hit)
        fn += int(real and not hit)
    # Falsos positivos sobre la propia serie normal (segunda mitad vs primera).
    half = len(normal) // 2
    normal_flagged = flagged_logs(normal[half:], normal[:half])
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    kinds = sorted({f.kind for f in findings})
    expected = abuse_meta.get("pattern") or []
    text = (
        "## Eval de anomalías — H5\n\n"
        f"- Baseline: {len(normal)} llamadas normales (7 días); "
        f"abuso: {len(abuse)} llamadas (~16 h).\n"
        f"- A nivel llamada: precisión {precision:.3f}, recall {recall:.3f} "
        f"(TP {tp}, FP {fp}, FN {fn}).\n"
        f"- Findings: {len(findings)} ({', '.join(kinds) or 'ninguno'}); "
        "patrones esperados del set: "
        f"{', '.join(str(p) for p in expected)}.\n"
        f"- Falsos positivos en la serie normal (2ª mitad vs 1ª): {len(normal_flagged)} llamadas.\n"
    )
    write_section(text)
    print(
        f"anomaly: precision={precision:.3f} recall={recall:.3f} (TP {tp} FP {fp} FN {fn}), "
        f"findings={[f.kind for f in findings]}, FP normales={len(normal_flagged)} -> {REPORT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
