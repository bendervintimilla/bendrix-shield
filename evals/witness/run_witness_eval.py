"""Eval del testigo de cámara (SAM 3.1) sobre cuadros reales etiquetados a mano.

RGPD: los cuadros son de clientes y empleados reales. Viven FUERA del repo
y entran solo por argumento; el reporte no lleva imágenes, cajas ni rutas
absolutas (solo el nombre del archivo). ``--redact-out`` escribe las
versiones redactadas en una carpeta que también debe estar fuera del repo,
para revisión humana.

Etiquetas: ``evals/witness/labels.json`` = ``{archivo: {people: N,
door_open: bool|null}}`` (claves que empiezan con ``_`` se ignoran).
Nombre de cuadro: ``<camara>_<YYYYmmdd-HHMMSS>.jpg`` (hora local de la Mac
que capturó; se rotula con la zona del sistema).

Uso (red real, ~USD 0.0025 por concepto y cuadro; la llave no se imprime):

    uv run python -m evals.witness.run_witness_eval \\
        --frames ~/Desktop/Hackathon-Meta/H20-camaras-reales/privado \\
        [--labels evals/witness/labels.json] [--no-door] [--limit N] \\
        [--redact-out /ruta/fuera/del/repo]

Escribe ``evals/recorded/witness-eval-<YYYY-mm-dd>.json``.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shield.witness.observe import DEFAULT_DOOR_CONCEPTS, observe  # noqa: E402

DEFAULT_LABELS = ROOT / "evals" / "witness" / "labels.json"
RECORDED = ROOT / "evals" / "recorded"
IMAGE_EXT = {".jpg", ".jpeg", ".png"}
_NAME_RE = re.compile(r"^(?P<camera>.+)_(?P<ts>\d{8}-\d{6})$")


def _inside_repo(path: Path) -> bool:
    try:
        path.expanduser().resolve().relative_to(ROOT)
        return True
    except ValueError:
        return False


def parse_frame_name(name: str) -> tuple[str, str]:
    """``cocina1_20261104-201500.jpg`` -> (``cocina1``, ISO con la zona del sistema)."""
    stem = Path(name).stem
    match = _NAME_RE.match(stem)
    if not match:
        return stem, ""
    naive = datetime.strptime(match.group("ts"), "%Y%m%d-%H%M%S")
    # La hora del nombre la pone la Mac que captura: zona local del sistema.
    return match.group("camera"), naive.astimezone().isoformat()


def percentile(values: list[float], pct: float) -> float | None:
    """Percentil por rango más cercano (sin interpolar)."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return round(ordered[rank - 1], 3)


def load_labels(path: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {k: dict(v) for k, v in data.items() if not k.startswith("_")}


def recorded_at(name: str, captured_at: str) -> str | None:
    """Hora que marca la cámara: en vivo = captura (Madrid); playback = la del nombre."""
    if not captured_at:
        return None
    from zoneinfo import ZoneInfo

    from shield.witness.surveillance import playback_time

    madrid = datetime.fromisoformat(captured_at).astimezone(ZoneInfo("Europe/Madrid"))
    if source_for(name) == "playback":
        return playback_time(Path(name).stem, madrid.isoformat()) or madrid.isoformat()
    return madrid.isoformat()


def source_for(name: str) -> str:
    """Cuadros nocturnos grabados = ``playback``; el resto, captura en vivo."""
    return "playback" if "noche" in Path(name).stem.lower() else "live_capture"


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def _count_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counted = [r for r in rows if r["ok"] and r["abs_error"] is not None]
    exact = sum(1 for r in counted if r["abs_error"] == 0)
    within1 = sum(1 for r in counted if r["abs_error"] <= 1)
    return {
        "n": len(counted),
        "exact": exact,
        "exact_rate": _rate(exact, len(counted)),
        "mae": round(sum(r["abs_error"] for r in counted) / len(counted), 4)
        if counted else None,
        "within_1": within1,
        "within_1_rate": _rate(within1, len(counted)),
    }


def _presence_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Decisión del autopiloto: hay alguien (people>0) vs vacío. Positivo = hay alguien."""
    scored = [r for r in rows if r["ok"] and r["expected_people"] is not None]
    tp = sum(1 for r in scored if r["people"] > 0 and r["expected_people"] > 0)
    fp = sum(1 for r in scored if r["people"] > 0 and r["expected_people"] == 0)
    fn = sum(1 for r in scored if r["people"] == 0 and r["expected_people"] > 0)
    tn = sum(1 for r in scored if r["people"] == 0 and r["expected_people"] == 0)
    return {
        "n": len(scored), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": _rate(tp, tp + fp), "recall": _rate(tp, tp + fn),
        "accuracy": _rate(tp + tn, len(scored)),
        # Vacío detectado correctamente (lo que dispara las reglas del testigo).
        "empty_precision": _rate(tn, tn + fn), "empty_recall": _rate(tn, tn + fp),
    }


def run_eval(
    frames_dir: Path,
    labels: dict[str, dict[str, Any]],
    *,
    site: str = "madrid",
    door: bool = True,
    limit: int | None = None,
    redact_out: Path | None = None,
    sam_fn: Any = None,
    meta_client: Any = None,
    budget_usd: float = 1.0,
) -> dict[str, Any]:
    """Corre ``observe`` en cada cuadro etiquetado y arma el reporte (sin imágenes)."""
    frames_dir = Path(frames_dir).expanduser()
    if redact_out is not None:
        redact_out = Path(redact_out).expanduser()
        if _inside_repo(redact_out):
            raise SystemExit("--redact-out debe estar FUERA del repo (RGPD)")
        redact_out.mkdir(parents=True, exist_ok=True)
    names = sorted(labels)
    if limit is not None:
        names = names[:limit]
    owns = sam_fn is None and meta_client is None
    guard = None
    if owns:
        import os

        from shield.meta_client import MetaClient
        from shield.witness.surveillance import BudgetGuard

        replay = os.environ.get("SHIELD_REPLAY_DIR") or str(
            frames_dir.parent / "replay-cache-privado")
        guard = BudgetGuard(MetaClient(replay_dir=replay), budget_usd)
        meta_client = guard
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    observations: list[dict[str, Any]] = []
    try:
        for name in names:
            path = frames_dir / name
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXT:
                missing.append(name)
                continue
            camera, captured_at = parse_frame_name(name)
            obs = observe(
                path.read_bytes(), camera=camera, site=site, room=camera,
                captured_at=captured_at or datetime.now(UTC).isoformat(),
                sam_fn=sam_fn, meta_client=meta_client,
                door_concepts=DEFAULT_DOOR_CONCEPTS if door else (),
                source=source_for(name),
            )
            observations.append({**obs.public(), "recorded_at": recorded_at(name, captured_at)})
            if redact_out is not None and obs.redacted_image:
                (redact_out / f"{Path(name).stem}.redacted.jpg").write_bytes(obs.redacted_image)
            label = labels[name]
            exp_people = label.get("people")
            exp_door = label.get("door_open")
            rows.append({
                "frame": Path(name).name,
                "camera": camera,
                "expected_people": exp_people,
                "people": obs.people,
                "abs_error": None if exp_people is None or not obs.ok
                else abs(int(obs.people) - int(exp_people)),
                "ambiguous": bool(label.get("ambiguous")),
                "expected_door_open": exp_door,
                "door_open": obs.door_open,
                "latency_ms": obs.latency_ms,
                "cost_usd": obs.cost_usd,
                "response_ids": list(obs.response_ids),
                "ok": obs.ok,
                "error": obs.error,
            })
    finally:
        if owns and meta_client is not None:
            meta_client.close()
        if redact_out is not None:  # fuera del repo: puede llevar cajas
            (redact_out / "observations.json").write_text(
                json.dumps(observations, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    meta = _meta(site, door, len(labels), missing)
    if guard is not None:
        meta["billed_usd"] = round(guard.spent, 6)
        meta["calls"] = dict(guard.calls)
    return {"meta": meta, "summary": summarize(rows), "frames": rows}


def _meta(site: str, door: bool, n_labels: int, missing: list[str]) -> dict[str, Any]:
    return {
        "eval": "witness-camera",
        "model": "sam-3.1",
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "site": site,
        "person_concepts": ["person"],
        "door_concepts": list(DEFAULT_DOOR_CONCEPTS) if door else [],
        "labels_total": n_labels,
        "labeled_frames_missing": [Path(m).name for m in missing],
        "privacy": "sin imágenes, cajas ni rutas absolutas; cuadros fuera del repo",
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if r["ok"]]
    counted = [r for r in ok if r["abs_error"] is not None]
    cameras = sorted({r["camera"] for r in rows})
    door_rows = [r for r in ok if r["expected_door_open"] is not None]
    decided = [r for r in door_rows if r["door_open"] is not None]
    latencies = [float(r["latency_ms"]) for r in ok]
    return {
        "frames": len(rows),
        "sam_errors": len(rows) - len(ok),
        "people_scored": len(counted),
        "people_exact": sum(1 for r in counted if r["abs_error"] == 0),
        "people_exact_rate": round(sum(1 for r in counted if r["abs_error"] == 0)
                                   / len(counted), 4) if counted else None,
        "people_mae": round(sum(r["abs_error"] for r in counted) / len(counted), 4)
        if counted else None,
        "people_within_1": sum(1 for r in counted if r["abs_error"] <= 1),
        "count": _count_metrics(rows),
        "count_unambiguous": _count_metrics([r for r in rows if not r.get("ambiguous")]),
        "count_by_camera": {c: _count_metrics([r for r in rows if r["camera"] == c])
                            for c in cameras},
        "presence": _presence_metrics(rows),
        "presence_by_camera": {c: _presence_metrics([r for r in rows if r["camera"] == c])
                               for c in cameras},
        "door_labeled": len(door_rows),
        "door_decided": len(decided),
        "door_abstained": len(door_rows) - len(decided),
        "door_correct": sum(1 for r in decided if r["door_open"] == r["expected_door_open"]),
        "door_accuracy_on_decided": round(
            sum(1 for r in decided if r["door_open"] == r["expected_door_open"]) / len(decided), 4)
        if decided else None,
        "latency_ms_p50": percentile(latencies, 50),
        "latency_ms_p95": percentile(latencies, 95),
        "cost_usd_total": round(sum(float(r["cost_usd"]) for r in rows), 6),
        "cost_usd_per_frame": round(sum(float(r["cost_usd"]) for r in rows) / len(rows), 6)
        if rows else None,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--frames", required=True, help="carpeta privada de cuadros (fuera del repo)")
    ap.add_argument("--labels", default=str(DEFAULT_LABELS))
    ap.add_argument("--site", default="madrid")
    ap.add_argument("--no-door", action="store_true", help="solo personas (1 pedido por cuadro)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--redact-out", default=None, help="carpeta para JPEG redactados (fuera)")
    ap.add_argument("--out", default=None, help="JSON de salida (por defecto evals/recorded)")
    ap.add_argument("--budget", type=float, default=1.0, help="tope facturado en USD")
    args = ap.parse_args(argv)

    frames = Path(args.frames).expanduser()
    if _inside_repo(frames):
        print("--frames debe estar FUERA del repo (RGPD)", file=sys.stderr)
        return 2
    labels = load_labels(Path(args.labels))
    if not labels:
        print(f"sin etiquetas en {Path(args.labels).name}: llénalo primero", file=sys.stderr)
        return 2
    report = run_eval(frames, labels, site=args.site, door=not args.no_door, limit=args.limit,
                      redact_out=Path(args.redact_out) if args.redact_out else None,
                      budget_usd=args.budget)
    out = Path(args.out).expanduser().resolve() if args.out else (
        RECORDED / f"witness-eval-{datetime.now(UTC).strftime('%Y-%m-%d')}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"reporte: {out.relative_to(ROOT) if _inside_repo(out) else out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
