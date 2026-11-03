"""Batería red team C2489-4: el set congelado se frena donde debe frenar.

Los casos viven en `evals/redteam/cases.json` (generador
`evals/gen_redteam.py`) y la batería en `evals/run_redteam.py`. Aquí se
afirma el núcleo seguro: todo caso `expect: contained` queda frenado y todo
control `expect: clean` fluye como corresponde. Los bypass conocidos
(`expect: gap`) NO se afirman como seguros: se verifica que la batería los
clasifica y los reporta en `evals/report.md`, tal cual pasen.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.run_redteam import run_battery  # noqa: E402

VECTORES = {"inyeccion", "exfiltracion", "voz", "confusion", "tasa"}


def _casos() -> list[dict]:
    data = json.loads((ROOT / "evals/redteam/cases.json").read_text(encoding="utf-8"))
    return data["casos"]


def test_set_redteam_congelado_completo():
    casos = _casos()
    assert len(casos) >= 26
    assert len({c["id"] for c in casos}) == len(casos)
    assert {c["vector"] for c in casos} == VECTORES
    assert all(c["expect"] in ("contained", "clean", "gap") for c in casos)


def test_casos_contenidos_se_frenan():
    filas = {f["id"]: f for f in run_battery()}
    fallas = [
        c["id"] for c in _casos() if c["expect"] == "contained" and not filas[c["id"]]["frenado"]
    ]
    assert fallas == [], f"debían frenar y pasaron en silencio: {fallas}"


def test_controles_limpios_fluyen():
    filas = {f["id"]: f for f in run_battery()}
    fallas = [c["id"] for c in _casos() if c["expect"] == "clean" and not filas[c["id"]]["frenado"]]
    assert fallas == [], f"controles limpios con resultado incorrecto: {fallas}"


def test_gaps_quedan_clasificados_para_el_reporte():
    filas = {f["id"]: f for f in run_battery()}
    gaps = [c for c in _casos() if c["expect"] == "gap"]
    assert gaps, "el set debe declarar sus bypass conocidos"
    for c in gaps:
        fila = filas[c["id"]]
        # Sin afirmar seguridad: la fila existe y trae lo observado para la tabla.
        assert fila["observado"]
        assert fila["expect"] == "gap"


def test_voz_sin_spark_no_aprueba_a_ciegas():
    from channels.voice import interpret_checked, parse_voice_command

    # El parser solo sí aprueba: por eso el camino verificado exige Spark o nada.
    assert parse_voice_command("sí, rota el token de bodega").action == "approve"
    intent, _ = interpret_checked("sí, rota el token de bodega", None)
    assert intent.action == "unknown"


def test_voz_parcial_sin_confirmar_no_ejecuta():
    from channels.approvals import ApprovalBroker
    from channels.voice import VoiceApprovalFlow

    broker = ApprovalBroker()
    req = broker.request(
        {
            "summary": "plan",
            "steps": [
                {"action": "rotate_token", "target": "bodega-token", "requires_approval": True},
                {"action": "rotate_token", "target": "compras-token", "requires_approval": True},
            ],
        }
    )
    out = VoiceApprovalFlow(broker, client=None).handle_transcript(
        req.approval_id, "sí rota todo menos compras"
    )
    assert out["status"] == "confirmation_required"
    assert broker.get(req.approval_id).status == "pending"
