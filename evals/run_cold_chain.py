"""Eval de cadena de frío (C2489-2): ataque IoT, voz y rotación 401.

Uso: ``uv run python evals/run_cold_chain.py``
Sin red ni créditos. Corre el escenario replay de
``crew/refrigeracion/scenario.py``, guarda la grabación pública en
``evals/recorded/cold-chain-replay.json`` (sin tokens en claro) y
agrega su sección a ``evals/report.md`` sin borrar las demás.

Mide: cambio legítimo aplicado, alcance mínimo (token ajeno no mueve
setpoint), 2 ataques de setpoint bloqueados sin mutar el equipo,
atacante 200 -> 401 tras la voz del dueño, y Refrigeración/Bodega/
Compras en 200 después de rotar solo Refrigeración.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crew.refrigeracion.scenario import run_scenario  # noqa: E402

REPORT = Path(__file__).parent / "report.md"
RECORDING = Path(__file__).parent / "recorded" / "cold-chain-replay.json"
MARKER = "## Cadena de frío (IoT) — C2489-2"


def _append_report(section: str) -> None:
    existing = REPORT.read_text(encoding="utf-8") if REPORT.is_file() else ""
    if MARKER in existing:
        start = existing.index(MARKER)
        nxt = existing.find("\n## ", start + len(MARKER))
        existing = (existing[:start] + (existing[nxt + 1 :] if nxt >= 0 else "")).rstrip() + "\n"
    REPORT.write_text(existing.rstrip() + "\n\n" + section, encoding="utf-8")


def main() -> int:
    result = run_scenario()
    RECORDING.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    s = result["statuses"]
    blocked = sum(
        1
        for step in result["steps"]
        if step["step"] == "stolen_token_attack"
        for a in step["attacks"]
        if a["decision"] == "block"
    )
    section = (
        f"{MARKER}\n\n"
        "Replay sin red ni créditos (USD 0). Escenario en "
        "`crew/refrigeracion/scenario.py`; grabación en "
        "`evals/recorded/cold-chain-replay.json` (sin tokens en claro). "
        "Reproducir: `uv run python evals/run_cold_chain.py`.\n\n"
        f"- Cambio legítimo (cámara 3 °C, 10:00, EC): aplicado, gateway {s['legit_gateway']}.\n"
        "- Alcance mínimo: token sin `coldchain:setpoint:camara` bloqueado, sin mutar el equipo.\n"
        f"- Ataques con token robado bloqueados: {blocked}/2 (cámara a 50 °C y congelador a 5 °C, "
        "03:00, origen BR); señales: fuera de rango, fuera de horario y origen inesperado.\n"
        f"- Atacante: {s['attacker_before']} -> {s['attacker_after']} tras rotar solo "
        "Refrigeración con confirmación por voz del dueño.\n"
        f"- Después de rotar: Refrigeración {s['refrigeracion_after']}, "
        f"Bodega {s['bodega_after']}, Compras {s['compras_after']}.\n"
        f"- Equipos al final: {result['final_equipment']}.\n"
        f"- Duración del escenario en esta corrida: {result['elapsed_s']} s.\n"
        "- Costo en créditos real: USD 0 (sin llamadas a modelos).\n"
    )
    _append_report(section)
    print(
        f"cold-chain: ataques bloqueados {blocked}/2, atacante "
        f"{s['attacker_before']}->{s['attacker_after']}, cocina "
        f"{s['refrigeracion_after']}/{s['bodega_after']}/{s['compras_after']} "
        f"-> {RECORDING}"
    )
    return 0 if result["ok"] and blocked == 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
