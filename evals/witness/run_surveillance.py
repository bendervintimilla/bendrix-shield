"""Vigilancia sobre cuadros reales: ocupación, fuera de horario, stock, caja y parte de turno.

RGPD: los cuadros viven FUERA del repo y entran por argumento. La salida
completa (``surveillance.json``, con cajas) va a la carpeta privada de
redactadas; el resumen publicable (``evals/recorded/surveillance-<fecha>.json``)
no lleva imágenes, cajas ni rutas absolutas. Muse Spark recibe solo imágenes
ya redactadas. Los eventos POS ``drawer_open`` son SIMULADOS y van rotulados.

Uso (red real; tope de gasto con --budget, la llave no se imprime):

    uv run python -m evals.witness.run_surveillance \\
        --frames /ruta/privado --out-dir /ruta/redactadas \\
        [--hours 12:00-00:30] [--budget 1.0] [--no-spark]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.witness.run_witness_eval import (  # noqa: E402
    IMAGE_EXT,
    _inside_repo,
    parse_frame_name,
    percentile,
)
from shield.witness.observe import WitnessObservation, observe  # noqa: E402
from shield.witness.redact import reencode_without_exif  # noqa: E402
from shield.witness.surveillance import (  # noqa: E402
    STOCK_CONCEPT_CANDIDATES,
    BudgetExceeded,
    BudgetGuard,
    OpeningHours,
    after_hours_check,
    alert_event,
    choose_stock_concept,
    count_concept,
    occupancy,
    playback_time,
    room_name,
    shift_report,
    stock_watch,
    unattended_cash_desk,
)

RECORDED = ROOT / "evals" / "recorded"


def base_camera(camera_raw: str) -> str:
    return re.sub(r"[-_]noche(-\d{4})?$", "", camera_raw)


def frame_info(name: str) -> dict[str, Any]:
    camera_raw, captured = parse_frame_name(name)
    stem = Path(name).stem
    playback = "noche" in stem.lower()
    at = (playback_time(stem, captured) if playback and captured else None) or captured
    cam = base_camera(camera_raw)
    return {"name": Path(name).name, "camera": cam, "room": cam, "captured_at": at,
            "file_time": captured, "source": "playback" if playback else "live_capture"}


def run(frames_dir: Path, out_dir: Path | None, *, hours: OpeningHours, site: str = "madrid",
        budget_usd: float = 1.0, stock_prefix: str = "almacen", cash_prefix: str = "caja",
        stock_trial_frames: int = 6, drop_threshold: float = 0.3, use_spark: bool = True,
        sam_fn: Any = None, spark_fn: Any = None, meta_client: Any = None,
        verified_empty: tuple[str, ...] = ()) -> dict[str, Any]:
    """Corre las 5 aplicaciones. Devuelve ``{"private": ..., "public": ...}``."""
    frames_dir = Path(frames_dir).expanduser()
    if out_dir is not None:
        out_dir = Path(out_dir).expanduser()
        if _inside_repo(out_dir):
            raise SystemExit("--out-dir debe estar FUERA del repo (RGPD)")
        out_dir.mkdir(parents=True, exist_ok=True)
    owns = sam_fn is None and meta_client is None
    if owns:
        from shield.meta_client import MetaClient

        meta_client = MetaClient(replay_dir=frames_dir.parent / "replay-cache-privado")
    stock_calls: list[dict[str, Any]] = []
    client = BudgetGuard(meta_client, budget_usd) if meta_client is not None else None
    files = sorted(p for p in frames_dir.iterdir()
                   if p.is_file() and p.suffix.lower() in IMAGE_EXT and _NAME_OK(p.name))
    infos = [frame_info(p.name) for p in files]
    observations: list[WitnessObservation] = []
    frame_rows: list[dict[str, Any]] = []
    try:
        # 1. ocupación (SAM 3.1, concepto person)
        for path, info in zip(files, infos, strict=True):
            obs = observe(path.read_bytes(), camera=info["camera"], site=site,
                          room=info["room"], captured_at=info["captured_at"], sam_fn=sam_fn,
                          meta_client=client, door_concepts=(), source=info["source"])
            observations.append(obs)
            if out_dir is not None and obs.redacted_image:
                (out_dir / f"{path.stem}.redacted.jpg").write_bytes(obs.redacted_image)
            frame_rows.append({"frame": info["name"], "camera": info["camera"],
                               "source": info["source"], "at": info["captured_at"],
                               "people": obs.people, "ok": obs.ok, "error": obs.error,
                               "latency_ms": obs.latency_ms, "cost_usd": obs.cost_usd,
                               "response_ids": obs.response_ids})
        by_name = {i["name"]: o for i, o in zip(infos, observations, strict=True)}

        # 2. fuera de horario
        alerts = [after_hours_check(o, hours) for o in observations]

        # 3. stock: elegir concepto con datos y comparar referencia vs actual.
        # Con cuadros nocturnos (playback 03:00) la referencia es la noche y el
        # actual es el vivo; sin ellos, el primer cuadro contra los siguientes.
        stock: dict[str, Any] = {"camera_prefix": stock_prefix, "frames": 0}
        stock_paths = sorted(((p, i) for p, i in zip(files, infos, strict=True)
                              if i["camera"].startswith(stock_prefix)),
                             key=lambda pi: pi[1]["captured_at"])
        if stock_paths:
            night = [pi for pi in stock_paths if pi[1]["source"] == "playback"]
            live = [pi for pi in stock_paths if pi[1]["source"] == "live_capture"]
            if night and live:
                groups = {"reference": night[:stock_trial_frames],
                          "current": live[:stock_trial_frames]}
                mode = "reference=playback 03:00, current=live"
            else:
                groups = {"reference": stock_paths[:1],
                          "current": stock_paths[1:1 + stock_trial_frames]}
                mode = "reference=first frame, current=later frames"
            counts: dict[str, dict[str, dict[str, int]]] = {
                c: {g: {} for g in groups} for c in STOCK_CONCEPT_CANDIDATES}
            for concept in STOCK_CONCEPT_CANDIDATES:
                for gname, members in groups.items():
                    for path, info in members:
                        try:
                            cc = count_concept(path.read_bytes(), concept, sam_fn=sam_fn,
                                               meta_client=client)
                        except BudgetExceeded:
                            continue
                        counts[concept][gname][info["name"]] = cc.count
                        stock_calls.append({"frame": info["name"], "group": gname,
                                            "concept": concept, "count": cc.count,
                                            "cost_usd": cc.cost_usd,
                                            "latency_ms": cc.latency_ms,
                                            "response_id": cc.response_id})
            choice = choose_stock_concept(
                {c: {g: list(v.values()) for g, v in gs.items() if v}
                 for c, gs in counts.items() if any(gs.values())})
            chosen = choice["chosen"]
            stock.update({"frames": len(stock_paths), "mode": mode,
                          "concept_choice": choice, "drop_threshold": drop_threshold})
            ref_counts = sorted(counts.get(chosen, {}).get("reference", {}).values())
            cur_counts = sorted(counts.get(chosen, {}).get("current", {}).values())
            if chosen and ref_counts and cur_counts:
                ref = ref_counts[len(ref_counts) // 2]  # mediana
                cur = cur_counts[len(cur_counts) // 2]
                cur_info = groups["current"][-1][1]
                actual = stock_watch(ref, cur, camera=cur_info["camera"], room=cur_info["room"],
                                     at=cur_info["captured_at"], hours=hours,
                                     drop_threshold=drop_threshold, concept=chosen)
                alerts.append(actual)
                # Contrafactual: la MISMA caída medida a una hora fuera de horario.
                closed_at = _closed_time(cur_info["captured_at"], hours)
                cf = stock_watch(ref, cur, camera=cur_info["camera"], room=cur_info["room"],
                                 at=closed_at, hours=hours, drop_threshold=drop_threshold,
                                 concept=chosen)
                from shield.autopilot import detect as _detect

                stock.update({
                    "reference_frames": len(ref_counts), "reference_counts": ref_counts,
                    "reference_median": ref, "current_frames": len(cur_counts),
                    "current_counts": cur_counts, "current_median": cur,
                    "measured_difference": cur - ref,
                    "actual": actual.to_dict(),
                    "counterfactual_after_hours": {
                        **cf.to_dict(), "counterfactual": True,
                        "autopilot_findings": [f.to_dict() for f in _detect(
                            [alert_event(cf)])] if cf.actionable else []},
                })

        # 4. caja desatendida: drawer_open POS SIMULADO 5 s después de cada cuadro de Caja
        cash: list[dict[str, Any]] = []
        for info in infos:
            if not info["camera"].startswith(cash_prefix):
                continue
            ts = (datetime.fromisoformat(info["captured_at"]) + timedelta(seconds=5)).isoformat()
            pos = {"action": "drawer_open", "ts": ts, "terminal": "pos-sim-1",
                   "camera": info["camera"], "room": info["room"], "simulated": True}
            alert = unattended_cash_desk(by_name[info["name"]], pos)
            alerts.append(alert)
            cash.append({"frame": info["name"], "pos_event": pos, "kind": alert.kind,
                         "severity": alert.severity})

        # Al autopiloto: solo alertas accionables.
        from shield.autopilot import run_pipeline

        events = [alert_event(a) for a in alerts if a.actionable]
        incident, contained = run_pipeline(events) if events else (None, None)
        autopilot = {
            "events": len(events),
            "incident_severity": incident.severity if incident else "none",
            "findings_by_kind": dict(Counter(f.kind for f in incident.findings))
            if incident else {},
            "scope_level": contained.scope_level if contained else "none",
            "detect_to_contain_ms": round(contained.detect_to_contain_ms, 3)
            if contained else None,
        }

        # 5. parte de turno con Muse Spark 1.3 (solo imágenes redactadas)
        occ = occupancy(observations)
        kinds = Counter(a.kind for a in alerts)
        facts = {
            "site": site,
            "opening_hours": hours.label(),
            "occupancy": {
                cam: {"people_latest": v["people"], "source": v["source"],
                      "frames": sum(1 for i in infos if i["camera"] == cam)}
                for cam, v in occ.items()},
            "alerts_by_kind": dict(kinds),
            "high_alerts": sum(1 for a in alerts if a.severity == "high"),
            "stock": {"concept": stock.get("concept_choice", {}).get("chosen"),
                      "reference_boxes_0300": stock.get("reference_median"),
                      "current_boxes_live": stock.get("current_median"),
                      "measured_difference": stock.get("measured_difference"),
                      "verdict": (stock.get("actual") or {}).get("kind"),
                      "same_drop_after_hours_would_be": (
                          stock.get("counterfactual_after_hours") or {}).get("kind")},
            "cash_desk_simulated_drawer_open": len(cash),
            "cash_desk_unattended": kinds.get("drawer_open_unattended", 0),
        }
        latest_per_cam: dict[str, WitnessObservation] = {}
        for o in observations:
            if o.ok and o.source == "live_capture" and (
                    o.camera not in latest_per_cam
                    or latest_per_cam[o.camera].captured_dt() <= o.captured_dt()):
                latest_per_cam[o.camera] = o
        report_facts = business_facts(stock=stock, cash=cash, alerts=alerts, hours=hours,
                                      live=latest_per_cam, autopilot=autopilot)
        facts["report_facts"] = report_facts
        # Imágenes (ya redactadas) de lo prioritario: caja desatendida y almacén.
        log_obs = _report_images(cash, stock, by_name)
        if use_spark and (spark_fn is not None or client is not None):
            log = shift_report(log_obs, report_facts, spark_fn=spark_fn,
                               meta_client=client if spark_fn is None else None)
        else:
            log = shift_report([], report_facts)
    finally:
        if owns and meta_client is not None:
            meta_client.close()

    verified: list[dict[str, Any]] = []
    if verified_empty and out_dir is not None:
        import hashlib

        for path, info, obs in zip(files, infos, observations, strict=True):
            if not any(path.name.startswith(pfx) for pfx in verified_empty):
                continue
            row = {"frame": info["name"], "camera": info["camera"], "source": info["source"],
                   "at": info["captured_at"], "sam_people": obs.people, "sam_ok": obs.ok,
                   "human_review": "vacía (revisión humana del orquestador)"}
            if obs.ok and obs.people == 0:  # humano y SAM coinciden: si no, no se publica
                clean = reencode_without_exif(path.read_bytes())
                out_name = f"{path.stem}.verified-empty.jpg"
                (out_dir / out_name).write_bytes(clean)
                row.update({"file": out_name, "sha256": hashlib.sha256(clean).hexdigest()})
            else:
                row["file"] = None
                row["withheld"] = "SAM no confirma 0 personas: se deja solo la redactada"
            verified.append(row)
        # Se AGREGA al verified-empty.json existente (otras entradas se conservan).
        target = out_dir / "verified-empty.json"
        try:
            previous = json.loads(target.read_text(encoding="utf-8")) if target.exists() else []
        except (OSError, json.JSONDecodeError):
            previous = []
        prev_list = previous if isinstance(previous, list) else previous.get("frames", [])
        mine = {v["frame"] for v in verified}
        merged = [v for v in prev_list if isinstance(v, dict) and v.get("frame") not in mine]
        merged += verified
        target.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")

    lat = [r["latency_ms"] for r in frame_rows if r["ok"]]
    sam_cost = sum(r["cost_usd"] for r in frame_rows) + sum(
        c["cost_usd"] for c in stock_calls)
    costs = {"sam_nominal_usd": round(sam_cost, 6), "spark_usd": round(log.cost_usd, 6),
             "nominal_total_usd": round(sam_cost + log.cost_usd, 6),
             "billed_usd": round(client.spent, 6) if client else None,
             "budget_usd": budget_usd, "calls": dict(client.calls) if client else {},
             "note": "nominal = precio de lista por llamada; billed = sin replays/caché"}
    meta = {"run_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "site": site, "opening_hours": hours.label(), "models": ["sam-3.1", "muse-spark-1.3"],
            "frames": len(files), "privacy": "sin imágenes, cajas ni rutas absolutas; Spark solo "
            "recibió imágenes redactadas; eventos POS simulados y rotulados"}
    by_cam: dict[str, dict[str, Any]] = {}
    for r in frame_rows:
        row = by_cam.setdefault(f"{r['camera']}:{r['source']}",
                                {"frames": 0, "people_max": 0, "frames_with_people": 0})
        row["frames"] += 1
        row["people_max"] = max(row["people_max"], r["people"])
        row["frames_with_people"] += int(r["people"] > 0)
    redacted_name = {i["name"]: f"{Path(i['name']).stem}.redacted.jpg" for i in infos}
    obs_name = {id(o): i["name"] for i, o in zip(infos, observations, strict=True)}
    cards = build_cards(stock=stock, stock_calls=stock_calls, cash=cash, alerts=alerts,
                        infos=infos, by_name=by_name, log=log,
                        log_images=[redacted_name[obs_name[id(o)]] for o in log_obs],
                        redacted_name=redacted_name, hours=hours)
    public = {
        **cards,
        "meta": meta,
        "occupancy_latest": occ,
        "occupancy_by_camera": by_cam,
        "alerts_by_kind": dict(Counter(a.kind for a in alerts)),
        "alerts_actionable": [a.to_dict() for a in alerts if a.actionable],
        "stock_detail": dict(stock),
        "cash_desk_detail": cash,
        "autopilot": autopilot,
        "security_log_detail": {**log.to_dict(), "facts": facts.get("report_facts", [])},
        "verified_empty": {"frames": len(verified),
                           "written": sum(1 for v in verified if v.get("file")),
                           "withheld": sum(1 for v in verified if not v.get("file"))},
        "latency_ms_p50": percentile(lat, 50),
        "latency_ms_p95": percentile(lat, 95),
        "costs": costs,
        "frames": frame_rows,
    }
    private = {**public, "observations": [
                   {**o.public(), "recorded_at": i["captured_at"]}
                   for i, o in zip(infos, observations, strict=True)],
               "stock_calls": stock_calls, "all_alerts": [a.to_dict() for a in alerts],
               "facts_for_spark": facts}
    return {"private": private, "public": public}


_WORDS = {0: "nobody", 1: "one person", 2: "two people"}


def _hhmm(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%H:%M")


def business_facts(*, stock: dict[str, Any], cash: list[dict[str, Any]], alerts: list[Any],
                   hours: OpeningHours, live: dict[str, WitnessObservation],
                   autopilot: dict[str, Any]) -> list[str]:
    """Hechos ya redactados en lenguaje de negocio (lo único que lee Muse Spark)."""
    facts: list[str] = []
    unattended = [c for c in cash if c["kind"] == "drawer_open_unattended"]
    if unattended:
        when = sorted({_hhmm(c["pos_event"]["ts"]) for c in unattended})
        at = when[0] if len(when) == 1 else f"{when[0]}-{when[-1]}"
        facts.append(
            f"Cash desk at {at}: 0 people on camera while the POS reported {len(unattended)} "
            "drawer openings (simulated test events) - needs review.")
        if autopilot.get("incident_severity") in ("high", "critical"):
            facts.append("The autopilot automatically contained the cash desk incident "
                         f"(severity {autopilot['incident_severity']}).")
    actual = stock.get("actual") or {}
    if actual:
        ref, cur = stock["reference_median"], stock["current_median"]
        cur_at = _hhmm(actual["at"])
        if actual["kind"] == "stock_drop_open_hours":
            facts.append(f"Storeroom: {ref} boxes at 03:00, {cur} at {cur_at}, during opening "
                         "hours - expected; the same drop after hours would raise an alert.")
        elif actual["kind"] == "stock_drop_after_hours":
            facts.append(f"Storeroom: {ref} boxes at 03:00, {cur} at {cur_at}, AFTER HOURS - "
                         "alert.")
        else:
            facts.append(f"Storeroom: {cur} boxes at {cur_at}, in line with the 03:00 "
                         f"reference of {ref}.")
    ah = [a for a in alerts if a.app == "after_hours" and a.kind != "open_hours"]
    if ah:
        people = [a for a in ah if a.kind == "after_hours_presence"]
        cams = {a.camera for a in ah}
        window = f"{hours.closes.strftime('%H:%M')}-{hours.opens.strftime('%H:%M')}"
        facts.append(
            f"After hours ({window}): {len(ah)} camera checks across {len(cams)} cameras, "
            + ("nobody on site." if not people else
               f"people seen in {len(people)} checks - alert."))
    parts = []
    for cam in ("cocina1", "cocina2", "pasillo", "caja1", "almacen"):
        obs = live.get(cam)
        if obs is None:
            continue
        if cam == "caja1" and obs.people > 0:
            state = "staff present"
        elif cam == "pasillo" and obs.people >= 3:
            state = "several people"
        elif obs.people == 0:
            state = "empty"
        else:
            state = _WORDS.get(obs.people, "several people")
        parts.append(f"{room_name(cam)} {state}")
    if parts:
        facts.append("Live now: " + ", ".join(parts) + ".")
    return facts


def _report_images(cash: list[dict[str, Any]], stock: dict[str, Any],
                   by_name: dict[str, WitnessObservation]) -> list[WitnessObservation]:
    names: list[str] = []
    unattended = [c["frame"] for c in cash if c["kind"] == "drawer_open_unattended"]
    names += unattended[:1]
    actual = stock.get("actual") or {}
    if actual:
        cur = [n for n, o in by_name.items() if o.camera == actual["camera"]
               and o.captured_at == actual["at"]]
        names += cur[:1]
        night = sorted(n for n, o in by_name.items() if o.camera == actual["camera"]
                       and o.source == "playback")
        names += night[:1]
    return [by_name[n] for n in names if n in by_name and by_name[n].redacted_image]


def _card(status: str, summary: str, summary_es: str, metric: str, *, image: str | None,
          model: str, response_ids: list[str], latency_ms: float, cost_usd: float,
          **extra: Any) -> dict[str, Any]:
    return {"status": status, "summary": summary, "summary_es": summary_es, "metric": metric,
            "image": image, "model": model, "response_ids": list(response_ids),
            "latency_ms": round(float(latency_ms), 3), "cost_usd": round(float(cost_usd), 6),
            **extra}


def build_cards(*, stock: dict[str, Any], stock_calls: list[dict[str, Any]],
                cash: list[dict[str, Any]], alerts: list[Any], infos: list[dict[str, Any]],
                by_name: dict[str, WitnessObservation], log: Any, log_images: list[str],
                redacted_name: dict[str, str], hours: OpeningHours) -> dict[str, Any]:
    """Tarjetas para la escena W2: status/summary/summary_es/metric/image/model/..."""
    cards: dict[str, Any] = {}
    # stock_watch
    chosen = (stock.get("concept_choice") or {}).get("chosen")
    actual = stock.get("actual") or {}
    calls = [c for c in stock_calls if c["concept"] == chosen]
    if not actual:
        cards["stock_watch"] = _card(
            "pending", "Stock watch pending: no storage frames counted.",
            "Vigilancia de stock pendiente: sin cuadros del almacén contados.", "n/a",
            image=None, model="sam-3.1", response_ids=[], latency_ms=0, cost_usd=0)
    else:
        ref, cur = stock["reference_median"], stock["current_median"]
        diff = stock["measured_difference"]
        status = {"stock_drop_after_hours": "alert", "stock_drop_open_hours": "expected"}.get(
            actual["kind"], "all_clear")
        cf = stock.get("counterfactual_after_hours") or {}
        cur_frame = max((c["frame"] for c in calls if c.get("group") == "current"),
                        default=None)
        cards["stock_watch"] = _card(
            status,
            f"SAM 3.1 '{chosen}': {ref} boxes at the 03:00 reference vs {cur} live "
            f"({diff:+d}). "
            + ("During opening hours -> expected, no alert. " if status == "expected" else "")
            + (f"The same drop after hours would be a {cf.get('severity', '').upper()} alert."
               if cf.get("actionable", cf.get("severity") in ("high", "critical")) else ""),
            f"SAM 3.1 '{chosen}': {ref} cajas en la referencia de las 03:00 frente a {cur} "
            f"en vivo ({diff:+d}). "
            + ("Durante el horario de apertura -> esperado, sin alerta. "
               if status == "expected" else "")
            + ("La misma caída fuera de horario sería alerta "
               f"{'alta' if cf.get('severity') == 'high' else cf.get('severity', '')}."
               if cf.get("severity") in ("high", "critical") else ""),
            f"{ref} → {cur} boxes",
            image=redacted_name.get(cur_frame) if cur_frame else None, model="sam-3.1",
            response_ids=[c["response_id"] for c in calls if c.get("response_id")],
            latency_ms=sum(c["latency_ms"] for c in calls) / len(calls) if calls else 0,
            cost_usd=sum(c["cost_usd"] for c in stock_calls),
            concept=chosen, counterfactual_status="alert" if cf.get("severity") in (
                "high", "critical") else "all_clear", hours=hours.label())
    # cash_desk
    unattended = [c for c in cash if c["kind"] == "drawer_open_unattended"]
    pick = (unattended or cash or [None])[0]
    if pick is None:
        cards["cash_desk"] = _card(
            "pending", "Cash desk check pending: no cash desk frames.",
            "Control de caja pendiente: sin cuadros de la Caja.", "n/a", image=None,
            model="sam-3.1", response_ids=[], latency_ms=0, cost_usd=0)
    else:
        obs = by_name[pick["frame"]]
        status = "alert" if unattended else "all_clear"
        cards["cash_desk"] = _card(
            status,
            (f"Cash drawer opened (SIMULATED POS event) with {obs.people} people at the cash "
             f"desk: irregularity ({len(unattended)} of {len(cash)} simulated openings)."
             if unattended else f"All {len(cash)} simulated drawer openings had staff present."),
            (f"Cajón abierto (evento POS SIMULADO) con {obs.people} personas en la Caja: "
             f"irregularidad ({len(unattended)} de {len(cash)} aperturas simuladas)."
             if unattended else
             f"Las {len(cash)} aperturas simuladas del cajón tenían personal presente."),
            f"{obs.people} people + drawer_open (simulated)",
            image=redacted_name.get(pick["frame"]), model="sam-3.1",
            response_ids=obs.response_ids, latency_ms=obs.latency_ms, cost_usd=obs.cost_usd,
            simulated=True)
    # after_hours
    ah = [a for a in alerts if a.app == "after_hours" and a.kind != "open_hours"]
    hits = [a for a in ah if a.kind == "after_hours_presence"]
    unavailable = [a for a in ah if a.kind == "witness_unavailable"]
    status = "alert" if hits or unavailable else ("all_clear" if ah else "pending")
    sample = (hits or ah or [None])[0]
    sample_name = None
    if sample is not None:
        sample_name = next((i["name"] for i in infos if i["captured_at"] == sample.at
                            and i["camera"] == sample.camera), None)
    sample_obs = by_name.get(sample_name) if sample_name else None
    cards["after_hours"] = _card(
        status,
        f"{len(ah)} frames outside opening hours ({hours.label()}): {len(hits)} with people.",
        f"{len(ah)} cuadros fuera del horario de apertura ({hours.label()}): "
        f"{len(hits)} con personas.",
        f"{len(hits)}/{len(ah)} after-hours frames with people",
        image=redacted_name.get(sample_name) if sample_name else None, model="sam-3.1",
        response_ids=sample_obs.response_ids if sample_obs else [],
        latency_ms=sample_obs.latency_ms if sample_obs else 0,
        cost_usd=sample_obs.cost_usd if sample_obs else 0)
    # security_log
    action_en = log.en[-1] if log.en else ""
    action_es = log.es[-1] if log.es else ""
    cards["security_log"] = _card(
        "alert" if log.valid and cash and any(
            c["kind"] == "drawer_open_unattended" for c in cash) else (
            "all_clear" if log.valid else "pending"),
        f"Owner report by {log.source} from {log.images_sent} redacted frames + business "
        f"facts ({'validated' if log.valid else 'not validated'}). {action_en}",
        f"Parte para el dueño de {log.source} con {log.images_sent} cuadros redactados + "
        f"hechos ({'validado' if log.valid else 'sin validar'}). {action_es}",
        f"{max(len(log.en) - 2, 0)} bullets EN/ES · {log.latency_ms / 1000:.1f} s",
        image=log_images[0] if log_images else None, model=log.source,
        response_ids=log.response_ids, latency_ms=log.latency_ms, cost_usd=log.cost_usd,
        text={"en": log.en, "es": log.es}, images=log_images)
    return cards


def _closed_time(at: str, hours: OpeningHours) -> str:
    """Primera media hora en punto, desde ``at``, en que el local está cerrado."""
    t = datetime.fromisoformat(at).replace(minute=0, second=0, microsecond=0)
    for _ in range(48):
        t += timedelta(minutes=30)
        if not hours.is_open(t):
            return t.isoformat()
    return at


def _NAME_OK(name: str) -> bool:  # noqa: N802
    return bool(re.match(r"^.+_\d{8}-\d{6}\.[A-Za-z]+$", name))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--frames", required=True)
    ap.add_argument("--out-dir", required=True, help="carpeta privada (fuera del repo)")
    ap.add_argument("--hours", default="12:00-00:30")
    ap.add_argument("--tz", default="Europe/Madrid")
    ap.add_argument("--site", default="madrid")
    ap.add_argument("--budget", type=float, default=1.0)
    ap.add_argument("--drop-threshold", type=float, default=0.3)
    ap.add_argument("--no-spark", action="store_true")
    ap.add_argument("--summary-out", default=None)
    ap.add_argument("--verified-empty", default="",
                    help="prefijos de cuadros con revisión humana de sala vacía (coma)")
    args = ap.parse_args(argv)
    frames = Path(args.frames).expanduser()
    if _inside_repo(frames):
        print("--frames debe estar FUERA del repo (RGPD)", file=sys.stderr)
        return 2
    out_dir = Path(args.out_dir).expanduser()
    result = run(frames, out_dir, hours=OpeningHours.parse(args.hours, args.tz), site=args.site,
                 budget_usd=args.budget, drop_threshold=args.drop_threshold,
                 use_spark=not args.no_spark,
                 verified_empty=tuple(p for p in args.verified_empty.split(",") if p))
    (out_dir / "surveillance.json").write_text(
        json.dumps(result["private"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = Path(args.summary_out).expanduser().resolve() if args.summary_out else (
        RECORDED / f"surveillance-{datetime.now().strftime('%Y-%m-%d')}.json")
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text(json.dumps(result["public"], ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    pub = result["public"]
    print(json.dumps({k: pub[k] for k in ("alerts_by_kind", "occupancy_by_camera", "autopilot",
                                          "costs", "latency_ms_p50", "latency_ms_p95")},
                     ensure_ascii=False, indent=2))
    text = pub["security_log"]["text"]
    print("\n".join(text["en"] + [""] + text["es"]))
    why = pub["stock_detail"].get("concept_choice", {}).get("why")
    print(f"stock: {json.dumps(why, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
