"""Eval de bodega de H7: SAM (replay sintético) + voz + diferencia.

Uso: ``uv run python evals/run_stock.py``
Sin red ni créditos y **sin tomas reales todavía**: las salidas SAM son
texto sintético con la gramática oficial (ver docs/SAM.md) y el dictado
de voz es texto replay. Cuando existan tomas reales de la bodega
(``evals/private/tomas.md``), esta misma eval corre contra SAM en vivo.

Mide: conteo en imagen, conteo en video por track IDs únicos, parseo del
dictado a ``[{item, qty, unit}]`` y la diferencia contra el teórico del
ledger. Agrega su sección a ``evals/report.md`` sin borrar las demás.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crew.bodega.agent import BodegaAgent  # noqa: E402
from crew.compras.ledger import Ledger  # noqa: E402
from shield.sdk.pending import PendingRegistry  # noqa: E402

REPORT = Path(__file__).parent / "report.md"
MARKER = "## Eval de bodega (SAM + voz) — H7"


def _box(obj: int, x: int) -> str:
    return f"{obj}<|box;x1={x};y1=2;x2={x + 9};y2=20;w=100;h=100|><|mask;x=0;y=0;data=5,5,~p{obj}|>"


def _append_report(section: str) -> None:
    existing = REPORT.read_text(encoding="utf-8") if REPORT.is_file() else ""
    if MARKER in existing:
        start = existing.index(MARKER)
        nxt = existing.find("\n## ", start + len(MARKER))
        existing = (existing[:start] + (existing[nxt + 1 :] if nxt >= 0 else "")).rstrip() + "\n"
    REPORT.write_text(existing.rstrip() + "\n\n" + section, encoding="utf-8")


def main() -> int:
    registry = PendingRegistry()
    ledger = Ledger()
    ledger.record_purchase(
        supplier="Eval",
        lines=[
            {"sku": "papa", "qty": 10, "unit_price": 1.5, "line_total": 15.0},
            {"sku": "huevo", "qty": 12, "unit_price": 0.2, "line_total": 2.4},
        ],
        subtotal=17.4,
        tax=0.0,
        total=17.4,
    )

    image_text = "<0f>" + ",".join(_box(i, i * 15) for i in range(3))
    video_text = "\n".join(
        [
            "<0f>" + ",".join([_box(0, 1), _box(1, 20)]),
            "<1f>" + _box(0, 2),
            "<2f>" + ",".join([_box(0, 3), _box(1, 22), _box(5, 40)]),
        ]
    )
    outputs = {"papa": image_text, "huevo": video_text}
    bodega = BodegaAgent(ledger, sam_fn=lambda prompt, media: outputs[prompt], registry=registry)

    image = bodega.count_stock({"kind": "image", "url": "replay://estante.png"}, ["papa"])
    video = bodega.count_stock({"kind": "video", "url": "replay://pasillo.mp4"}, ["huevo"])
    image_count = int(image["counts"][0]["count"])
    video_count = int(video["counts"][0]["count"])  # IDs únicos: 0, 1, 5
    video_tracks = list(video["counts"][0]["track_ids"])

    heard = bodega.transcribe("diez papas, doce huevos")
    heard_map = {item["item"]: item["qty"] for item in heard["items"]}
    diff = bodega.diff_stock({"papa": float(image_count), "huevo": float(video_count)})

    ok_image = image_count == 3
    ok_video = video_count == 3 and video_tracks == [0, 1, 5]
    ok_voice = heard_map.get("papas") == 10.0 and heard_map.get("huevos") == 12.0
    ok_diff = diff["has_diff"] is True  # contado != teórico a propósito
    cost = float(image["cost_usd"]) + float(video["cost_usd"])

    section = (
        f"{MARKER}\n\n"
        "Replay sin red. **No hay tomas reales de bodega todavía** (la "
        "lista por grabar está en `evals/private/tomas.md`): las salidas "
        "SAM son texto sintético con la gramática oficial de "
        "`docs/SAM.md` y la voz es texto replay, no audio real.\n\n"
        f"- Conteo en imagen (esperado 3): {image_count} "
        f"({'ok' if ok_image else 'FALLA'})\n"
        f"- Conteo en video por track IDs (esperado 3 únicos [0, 1, 5]): "
        f"{video_count} {video_tracks} ({'ok' if ok_video else 'FALLA'})\n"
        f"- Dictado a ítems (esperado papas=10, huevos=12): {heard_map} "
        f"({'ok' if ok_voice else 'FALLA'})\n"
        f"- Diferencia contra el teórico detectada: "
        f"{'sí' if ok_diff else 'no'} (filas: {diff['rows']})\n"
        f"- Costo SAM teórico de la eval: USD {cost:.4f} "
        "(imagen USD 0,0025 + video al mínimo de 50 frames USD 0,01, "
        "por concepto; en replay no se factura)\n"
        "- Costo en créditos real: USD 0 (sin llamadas a modelos).\n"
    )
    _append_report(section)
    print(
        f"stock: imagen {image_count} (esp. 3), video {video_count} {video_tracks} "
        f"(esp. 3 [0, 1, 5]), voz {heard_map}, diff {'ok' if ok_diff else 'FALLA'} -> {REPORT}"
    )
    return 0 if (ok_image and ok_video and ok_voice and ok_diff) else 1


if __name__ == "__main__":
    raise SystemExit(main())
