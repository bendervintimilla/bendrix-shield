"""Eval de cadena de frío (C2489-2): ataque IoT, voz y rotación 401.

Uso: ``uv run python evals/run_cold_chain.py``
Sin red ni créditos. Corre el escenario replay de
``crew/refrigeracion/scenario.py``, guarda la grabación pública en
``evals/recorded/cold-chain-replay.json`` (sin tokens en claro) y
reemplaza su sección de ``evals/report.md`` en el mismo lugar, sin borrar
las demás.

Idempotente: si lo medido no cambió (solo cambian la duración y el
``token_id`` nuevo, que son aleatorios en cada corrida), la grabación y el
informe quedan intactos byte a byte. Así ``make demo`` no deja cambios en
el árbol de trabajo.

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
# Campos que cambian en cada corrida sin que cambie lo medido.
VOLATILE_KEYS = frozenset({"elapsed_s", "new_token_id"})


def _stable(obj: object) -> object:
    """Copia sin los campos volátiles, para comparar dos corridas."""
    if isinstance(obj, dict):
        return {k: _stable(v) for k, v in obj.items() if k not in VOLATILE_KEYS}
    if isinstance(obj, list):
        return [_stable(v) for v in obj]
    return obj


def _save_recording(result: dict, path: Path = RECORDING) -> tuple[dict, bool]:
    """Escribe la grabación solo si lo medido cambió.

    Devuelve la grabación vigente (la nueva o la que ya estaba) y si se
    escribió. Con lo medido igual se conserva el archivo tal cual.
    """
    if path.is_file():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old = None
        if isinstance(old, dict) and _stable(old) == _stable(result):
            return old, False
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result, True


def _replace_report_section(section: str, report: Path = REPORT) -> None:
    """Reemplaza la sección en su lugar (o la agrega al final si no está).

    La sección termina donde empieza el siguiente título ``## `` o el
    siguiente marcador ``<!-- ``, para no comerse los marcadores de otras
    secciones. Si el texto resultante es igual, no reescribe el archivo.
    """
    existing = report.read_text(encoding="utf-8") if report.is_file() else ""
    if MARKER in existing:
        start = existing.index(MARKER)
        ends = [
            i
            for i in (
                existing.find("\n## ", start + len(MARKER)),
                existing.find("\n<!-- ", start + len(MARKER)),
            )
            if i >= 0
        ]
        if ends:
            end = min(ends) + 1
            updated = existing[:start] + section + "\n" + existing[end:]
        else:
            updated = existing[:start] + section
    else:
        updated = existing.rstrip() + "\n\n" + section
    if updated != existing:
        report.write_text(updated, encoding="utf-8")


def main() -> int:
    measured = run_scenario()
    result, written = _save_recording(measured)
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
    _replace_report_section(section)
    rel = RECORDING.resolve().relative_to(Path(__file__).resolve().parents[1])
    print(
        f"cold-chain: ataques bloqueados {blocked}/2, atacante "
        f"{s['attacker_before']}->{s['attacker_after']}, cocina "
        f"{s['refrigeracion_after']}/{s['bodega_after']}/{s['compras_after']} "
        f"-> {rel} ({'actualizada' if written else 'sin cambios en lo medido'}; "
        f"esta corrida {measured['elapsed_s']} s)"
    )
    return 0 if result["ok"] and blocked == 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
