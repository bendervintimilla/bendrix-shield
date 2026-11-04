"""Vigilancia con cámaras reales para la escena «Sentinel» (Clara del Rey, Madrid).

Lee lo que deja ``shield/witness`` (W1) en ``SHIELD_WITNESS_DIR``:

- ``observations.json``: observaciones en el formato de
  ``WitnessObservation.public()`` (lista o ``{"observations": [...]}``).
- ``<camera>_<YYYYmmdd-HHMMSS>.redacted.jpg``: cuadro YA redactado de cada
  observación (personas tapadas). Esta capa nunca ve la imagen cruda.
- ``*.verified-empty.jpg`` + ``verified-empty.json``: cuadros vacíos que una
  persona verificó uno a uno (el redactor difumina todo si no hay cajas).
- ``surveillance.json`` (opcional): tarjetas que W1 genere (almacén, caja,
  parte de seguridad de Muse Spark). Lo que falte se muestra «pending».
- ``latest.jpg``: compatibilidad; último cuadro redactado si no hay otro.

La precisión medida sale de ``evals/recorded/witness-eval-*.json`` del repo.
Sin carpeta ni datos, la sección queda en «pending» y la escena sigue igual.
Al navegador solo salen campos públicos en lista blanca: nunca rutas,
bytes ni cajas.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

WITNESS_DIR_ENV = "SHIELD_WITNESS_DIR"
OBS_FILE = "observations.json"
SURV_FILE = "surveillance.json"
VERIFIED_FILE = "verified-empty.json"
IMAGE_FILE = "latest.jpg"
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_JSON_BYTES = 2 * 1024 * 1024
DEFAULT_SITE = "Clara del Rey, Madrid"
PLAYBACK_SOURCES = {"playback", "recorded", "replay", "recording"}
LIVE_SOURCES = {"live", "live_capture", "camera"}
AFTER_HOURS = range(0, 6)  # 00:00–05:59, hora del sitio
# Medido por el orquestador el 4-nov: la cámara marcaba 21:22 con la Mac en
# 20:56. ``surveillance.json`` puede corregirlo con meta.camera_clock_ahead_min.
CAMERA_CLOCK_AHEAD_MIN = 26
EVAL_GLOB = "witness-eval-*.json"
REPO_ROOT = Path(__file__).resolve().parent.parent
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,150}$")
_REC_TIME = re.compile(r"(?:^|[-_])(\d{2})(\d{2})$")

PLACEHOLDER_SVG = (
    b"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 640 360' width='640' height='360'>"
    b"<rect width='640' height='360' fill='#0c1016'/>"
    b"<rect x='1' y='1' width='638' height='358' fill='none' stroke='#2f3946' "
    b"stroke-dasharray='8 6'/>"
    b"<g fill='none' stroke='#6c7787' stroke-width='6' stroke-linejoin='round'>"
    b"<rect x='262' y='140' width='116' height='76' rx='10'/>"
    b"<circle cx='320' cy='178' r='22'/><path d='M290 140l10-16h40l10 16'/></g>"
    b"<text x='320' y='262' fill='#9aa5b4' font-family='sans-serif' font-size='20' "
    b"text-anchor='middle'>No camera frame yet</text></svg>"
)

ROOM_NAMES = {  # base de la cámara -> (EN, ES)
    "cocina": ("Kitchen", "Cocina"), "kitchen": ("Kitchen", "Cocina"),
    "pasillo": ("Hallway", "Pasillo"), "hallway": ("Hallway", "Pasillo"),
    "caja": ("Cash desk", "Caja"), "barra": ("Bar", "Barra"),
    "almacen": ("Storeroom", "Almacén"), "almacén": ("Storeroom", "Almacén"),
}


# -- utilidades -------------------------------------------------------------
def witness_dir() -> Path | None:
    raw = (os.environ.get(WITNESS_DIR_ENV) or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_dir() else None


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _short_id(value: Any) -> str:
    text = str(value or "").strip()
    return text if len(text) <= 14 else text[:12] + "…"


def _text(value: Any, limit: int = 400) -> str:
    return str(value).strip()[:limit] if isinstance(value, (str, int, float)) else ""


def _read_json(path: Path) -> Any:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JSON_BYTES:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def safe_image(base: Path | None, name: str | None) -> bytes | None:
    """JPEG de ``base/name`` solo si el nombre es simple, está dentro y es JPEG."""
    if base is None or not name or not _SAFE_NAME.match(name) or ".." in name:
        return None
    path = base / name
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_IMAGE_BYTES:
            return None
        if path.resolve().parent != base.resolve():
            return None
        data = path.read_bytes()
    except OSError:
        return None
    return data if data[:3] == b"\xff\xd8\xff" else None


def model_label(model: str) -> str:
    low = model.strip().lower()
    if low.startswith("sam"):
        return "SAM " + low[3:].lstrip("-_ ")
    if "spark" in low:
        return "Muse Spark"
    return model.strip() or "SAM 3.1"


def _base_and_time(camera: str) -> tuple[str, str]:
    """``cocina1-noche-0300`` -> (``cocina1``, ``03:00``); sin hora -> (camera, "")."""
    m = _REC_TIME.search(camera)
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return camera, ""
    base = camera[: m.start()]
    base = re.sub(r"[-_](noche|night|madrugada)$", "", base)
    return base or camera, f"{m.group(1)}:{m.group(2)}"


def room_label(camera: str, es: bool) -> str:
    base, _ = _base_and_time(camera)
    m = re.match(r"^([a-zA-Zéá]+)[-_ ]?(\d*)$", base)
    word, num = (m.group(1).lower(), m.group(2)) if m else (base.lower(), "")
    names = ROOM_NAMES.get(word)
    name = names[1 if es else 0] if names else base.replace("-", " ").replace("_", " ").title()
    return f"{name} {num}".strip()


# -- observaciones ----------------------------------------------------------
def public_observation(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normaliza una observación pública; ``None`` si no sirve como testimonio."""
    if not isinstance(raw, dict):
        return None
    if raw.get("ok") is False or raw.get("error"):
        return None  # SAM falló: no hay testimonio válido (no afirmar «0 personas»)
    ts = _parse_ts(raw.get("captured_at"))
    people = raw.get("people")
    if ts is None or isinstance(people, bool) or not isinstance(people, int) or people < 0:
        return None
    camera = str(raw.get("camera") or "").strip()[:60]
    if not _SAFE_NAME.match(camera or "x"):
        camera = re.sub(r"[^A-Za-z0-9._-]", "", camera)[:60]
    source = str(raw.get("source") or "").strip().lower()
    door = raw.get("door_open")
    response_ids = raw.get("response_ids") or []
    if isinstance(response_ids, str):
        response_ids = [response_ids]
    base, rec_hhmm = _base_and_time(camera)
    rec = _parse_ts(raw.get("recorded_at"))
    if rec is not None:
        rec_hhmm = rec.strftime("%H:%M")
    elif source in PLAYBACK_SOURCES and not rec_hhmm:
        rec_hhmm = ""
    site = str(raw.get("site") or "").strip()
    return {
        "camera": camera,
        "room_key": base,
        "room_en": room_label(camera, False),
        "room_es": room_label(camera, True),
        "site": DEFAULT_SITE if site.lower() in ("", "madrid") else site[:80],
        "captured_at": ts.isoformat(),
        "captured_hhmm": ts.strftime("%H:%M"),
        "recorded_hhmm": rec_hhmm,
        "people": people,
        "door_open": door if isinstance(door, bool) else None,
        "model": model_label(str(raw.get("model") or "")),
        "response_id_short": _short_id(response_ids[0]) if response_ids else "",
        "latency_ms": _num(raw.get("latency_ms")),
        "cost_usd": _num(raw.get("cost_usd")),
        "source": source,
        "is_live": source in LIVE_SOURCES,
        "is_playback": source in PLAYBACK_SOURCES,
        "is_fixture": source not in LIVE_SOURCES and source not in PLAYBACK_SOURCES,
        "_ts": ts,
        "_image": f"{camera}_{ts.strftime('%Y%m%d-%H%M%S')}.redacted.jpg",
    }


def load_observations(base: Path | None = None) -> list[dict[str, Any]]:
    """Observaciones públicas válidas, de la más vieja a la más nueva."""
    base = base or witness_dir()
    if base is None:
        return []
    data = _read_json(base / OBS_FILE)
    if isinstance(data, dict):
        data = data.get("observations", [data] if "captured_at" in data else [])
    if not isinstance(data, list):
        return []
    out = [o for o in (public_observation(r) for r in data) if o is not None]
    out.sort(key=lambda o: o["_ts"])
    return out


def verified_empty(base: Path | None) -> set[str]:
    """Archivos que una persona verificó vacíos (``people_human_verified == 0``)."""
    if base is None:
        return set()
    data = _read_json(base / VERIFIED_FILE)
    rows = data if isinstance(data, list) else (data or {}).get("files", []) \
        if isinstance(data, dict) else []
    def human_empty(r: dict[str, Any]) -> bool:
        # Formatos de W1: ``people_human_verified: 0`` o ``human_review`` + ``sam_people: 0``.
        if r.get("people_human_verified") == 0:
            return True
        return bool(r.get("human_review")) and r.get("sam_people") == 0
    return {
        str(r.get("file")) for r in rows
        if isinstance(r, dict) and human_empty(r)
        and _SAFE_NAME.match(str(r.get("file") or ""))
    }


def _verified_name(obs: dict[str, Any]) -> str:
    return obs["_image"].replace(".redacted.jpg", ".verified-empty.jpg")


def strip_private(obs: dict[str, Any] | None) -> dict[str, Any] | None:
    if obs is None:
        return None
    return {k: v for k, v in obs.items() if not k.startswith("_")}


def _proof(obs: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": obs["model"], "response_id_short": obs["response_id_short"],
        "latency_ms": obs["latency_ms"], "cost_usd": obs["cost_usd"],
    }


# -- precisión medida (eval real del repo) ---------------------------------
def eval_summary(root: Path = REPO_ROOT) -> dict[str, Any] | None:
    """Fila de precisión desde el eval grabado más reciente (sin inventar)."""
    files = sorted((root / "evals" / "recorded").glob(EVAL_GLOB))
    if not files:
        return None
    data = _read_json(files[-1])
    if not isinstance(data, dict) or not isinstance(data.get("summary"), dict):
        return None
    s = data["summary"]
    pres = s.get("presence") or {}
    count = s.get("count") or {}
    groups: dict[str, dict[str, int]] = {}
    for cam, v in (s.get("count_by_camera") or {}).items():
        g = groups.setdefault(_base_and_time(cam)[0], {"n": 0, "exact": 0, "within_1": 0})
        for k in g:
            g[k] += int(v.get(k) or 0)
    perfect = {k: v for k, v in groups.items() if v["n"] and v["exact"] == v["n"]}
    imperfect = {k: v for k, v in groups.items() if v["n"] and v["exact"] < v["n"]}
    kitchens = [v for k, v in groups.items() if k.startswith(("cocina", "kitchen"))]
    n_pres = int(pres.get("n") or 0)
    return {
        "run_date": str((data.get("meta") or {}).get("run_at") or "")[:10],
        "model": model_label(str((data.get("meta") or {}).get("model") or "")),
        "frames": int(s.get("frames") or 0),
        "presence_ok": int(pres.get("tp") or 0) + int(pres.get("tn") or 0),
        "presence_n": n_pres,
        "presence_precision": pres.get("precision"), "presence_recall": pres.get("recall"),
        "exact": int(count.get("exact") or s.get("people_exact") or 0),
        "within_1": int(count.get("within_1") or s.get("people_within_1") or 0),
        "count_n": int(count.get("n") or s.get("people_scored") or 0),
        "kitchen_exact": sum(v["exact"] for v in kitchens),
        "kitchen_n": sum(v["n"] for v in kitchens),
        "perfect": {
            "rooms_en": [room_label(k, False) for k in sorted(perfect, key=_room_order)],
            "rooms_es": [room_label(k, True) for k in sorted(perfect, key=_room_order)],
            "exact": sum(v["exact"] for v in perfect.values()),
            "n": sum(v["n"] for v in perfect.values()),
        },
        "others": [
            {"room_en": room_label(k, False), "room_es": room_label(k, True),
             "exact": v["exact"], "within_1": v["within_1"], "n": v["n"]}
            for k, v in sorted(imperfect.items(), key=lambda kv: _room_order(kv[0]))
        ],
        "latency_p50_ms": s.get("latency_ms_p50"),
        "cost_per_frame_usd": s.get("cost_usd_per_frame"),
    }


# -- tarjetas de vigilancia --------------------------------------------------
def _engine_check_unattended(night: dict[str, Any]) -> dict[str, Any]:
    """Regla real del autopiloto con la observación nocturna real.

    Un deshielo remoto en esa sala en el instante del cuadro: con 0 personas
    el motor debe marcar ``unattended_remote_physical_command``.
    """
    try:
        from shield.autopilot import camera_event, detect, from_cold_room
    except ImportError:  # sin la rama del testigo
        return {"available": False}
    ts = night["_ts"]
    pub = {"camera": night["camera"], "site": "madrid", "room": night["camera"],
           "captured_at": night["captured_at"], "people": night["people"],
           "door_open": night["door_open"], "ok": True, "source": night["source"]}
    cmd = from_cold_room({
        "actor": "refrigeracion", "action": "defrost", "target": night["camera"],
        "duration_min": 240, "source": "agent", "ts": ts + timedelta(seconds=1),
        "site": "madrid", "room": night["camera"],
    })
    kinds = sorted({f.kind for f in detect([camera_event(pub), cmd])
                    if f.kind.startswith(("unattended", "on_site"))})
    return {"available": True, "findings": kinds}


def _card(key: str, status: str, **fields: Any) -> dict[str, Any]:
    return {"key": key, "status": status, **fields}


def _room_order(key: str) -> tuple[int, str]:
    order = ("cocina", "kitchen", "pasillo", "hallway", "caja", "barra", "almacen")
    word = re.sub(r"\d+$", "", key)
    return (order.index(word) if word in order else len(order), key)


def _occupancy(obs: list[dict[str, Any]]) -> dict[str, Any]:
    live = [o for o in obs if o["is_live"]]
    if not live:
        return _card("occupancy", "pending")
    rooms: dict[str, dict[str, Any]] = {}
    frames: dict[str, int] = {}
    for o in live:
        rooms[o["room_key"]] = o
        frames[o["room_key"]] = frames.get(o["room_key"], 0) + 1
    # Cuadro por defecto: la sala con más gente (muestra la redacción); una sala
    # vacía sale difuminada entera por el redactor y no enseña nada.
    last = max(rooms.values(), key=lambda o: (o["people"], o["_ts"]))
    return _card(
        "occupancy", "live",
        image=f"/sentinel/surveillance/room/{last['room_key']}.jpg",
        rooms=[{"room_en": o["room_en"], "room_es": o["room_es"], "people": o["people"],
                "frames": frames[k], "hhmm": o["recorded_hhmm"],
                "image": f"/sentinel/surveillance/room/{k}.jpg"}
               for k, o in sorted(rooms.items(), key=lambda kv: _room_order(kv[0]))],
        frames=len(live),
        image_room_en=last["room_en"], image_room_es=last["room_es"],
        image_people=last["people"],
        **_proof(last),
    )


def _night(obs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [o for o in obs if o["is_playback"] and o["recorded_hhmm"]
            and int(o["recorded_hhmm"][:2]) in AFTER_HOURS]


def _night_pick(night: list[dict[str, Any]], verified: set[str]) -> dict[str, Any]:
    occupied = [o for o in night if o["people"] > 0]
    if occupied:
        return occupied[-1]
    checked = [o for o in night if _verified_name(o) in verified]
    return (checked or night)[-1]


def _after_hours(obs: list[dict[str, Any]], verified: set[str]) -> dict[str, Any]:
    night = _night(obs)
    if not night:
        return _card("after_hours", "pending")
    occupied = [o for o in night if o["people"] > 0]
    pick = _night_pick(night, verified)
    rooms: dict[str, dict[str, Any]] = {}
    for o in night:
        r = rooms.setdefault(o["room_key"], {"room_en": o["room_en"], "room_es": o["room_es"],
                                             "people_max": 0, "frames": 0})
        r["people_max"] = max(r["people_max"], o["people"])
        r["frames"] += 1
    return _card(
        "after_hours", "alert" if occupied else "all_clear",
        image="/sentinel/surveillance/after_hours.jpg",
        room_en=pick["room_en"], room_es=pick["room_es"],
        rooms=[rooms[k] for k in sorted(rooms, key=_room_order)],
        recorded_hhmm=pick["recorded_hhmm"], people=pick["people"],
        frames=len(night), frames_empty=sum(1 for o in night if o["people"] == 0),
        human_verified=_verified_name(pick) in verified,
        engine=_engine_check_unattended(pick) if not occupied else {"available": False},
        **_proof(pick),
    )


_SURV_KEYS = {
    "stock_watch": ("stock_watch", "stock", "storeroom", "almacen"),
    "cash_desk": ("cash_desk", "unattended_cash_desk", "caja"),
    "security_log": ("security_log", "spark_log", "spark_security_log", "parte"),
}
_SURV_FIELDS = ("status", "summary", "summary_es", "metric", "metric_es", "text", "text_es",
                "captured_at", "hhmm", "people", "boxes", "boxes_before", "boxes_after",
                "pos_event", "inputs")


def _from_surveillance(key: str, surv: dict[str, Any], base: Path | None,
                       by_image: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    raw = next((surv[k] for k in _SURV_KEYS[key] if isinstance(surv.get(k), dict)), None)
    if raw is None:
        return _card(key, "pending")
    card = {f: (_text(raw[f], 2000) if isinstance(raw[f], str) else raw[f])
            for f in _SURV_FIELDS if f in raw and isinstance(raw[f], (str, int, float))
            and not isinstance(raw[f], bool)}
    text = raw.get("text")
    if isinstance(text, dict):  # {"en": [...], "es": [...]} (viñetas) o {"en": "..."}
        for lang in ("en", "es"):
            val = text.get(lang)
            if isinstance(val, str):
                val = val.splitlines()
            lines = val if isinstance(val, list) else []
            lines = [_text(x, 500) for x in lines if isinstance(x, str) and x.strip()][:20]
            if lines:
                card[f"lines_{lang}"] = lines
        card.pop("text", None)
    elif isinstance(text, str) and text.strip():
        card["lines_en"] = [_text(x, 500) for x in text.splitlines() if x.strip()][:20]
        card.pop("text", None)
    status = str(card.pop("status", "") or "ok").lower()[:20]
    card["simulated"] = raw.get("simulated") is True
    image = str(raw.get("image") or raw.get("image_file") or "")
    has_img = safe_image(base, image) is not None
    seen = (by_image or {}).get(image)
    if seen is not None and seen["recorded_hhmm"]:
        card["hhmm"] = seen["recorded_hhmm"]
    ids = raw.get("response_ids") or raw.get("response_id") or []
    ids = [ids] if isinstance(ids, str) else ids
    return _card(
        key, status if status in ("ok", "all_clear", "alert", "live", "pending", "expected")
        else "ok",
        image=f"/sentinel/surveillance/{key}.jpg" if has_img else None,
        model=model_label(str(raw.get("model") or "")) if raw.get("model") else "",
        response_id_short=_short_id(ids[0]) if ids else "",
        response_count=len(ids),
        latency_ms=_num(raw.get("latency_ms")), cost_usd=_num(raw.get("cost_usd")),
        **card,
    )


def load_surveillance(base: Path | None) -> dict[str, Any]:
    data = _read_json(base / SURV_FILE) if base is not None else None
    return data if isinstance(data, dict) else {}


def surveillance_state(base: Path | None = None) -> dict[str, Any]:
    """Sección «Surveillance»: 5 tarjetas + fila de precisión, todo público."""
    base = base or witness_dir()
    obs = load_observations(base)
    surv = load_surveillance(base)
    verified = verified_empty(base)
    by_image = {o["_image"]: o for o in obs}
    cards = [
        _occupancy(obs),
        _after_hours(obs, verified),
        _from_surveillance("stock_watch", surv, base, by_image),
        _from_surveillance("cash_desk", surv, base, by_image),
        _from_surveillance("security_log", surv, base, by_image),
    ]
    real = [o for o in obs if not o["is_fixture"]]
    models = sorted({o["model"] for o in real})
    if cards[-1]["status"] != "pending":
        models.append(cards[-1].get("model") or "Muse Spark")
    stats = {
        "cameras": len({o["room_key"] for o in real}),
        "frames": len(real),
        "models": ["Meta " + " + ".join(models)] if models else [],
    }
    ahead = (surv.get("meta") or {}).get("camera_clock_ahead_min") \
        if isinstance(surv.get("meta"), dict) else None
    stats["camera_clock_ahead_min"] = (
        ahead if isinstance(ahead, (int, float)) and not isinstance(ahead, bool)
        else CAMERA_CLOCK_AHEAD_MIN) if real else None
    return {"available": bool(obs), "cards": cards, "eval": eval_summary(), "stats": stats}


def surveillance_image(key: str, base: Path | None = None) -> bytes | None:
    """Imagen redactada de una tarjeta. Nunca acepta rutas del cliente."""
    base = base or witness_dir()
    if base is None:
        return None
    obs = load_observations(base)
    if key == "occupancy":
        live = [o for o in obs if o["is_live"]]
        if live:
            return safe_image(base, live[-1]["_image"])
        return safe_image(base, IMAGE_FILE)
    if key == "after_hours":
        night = _night(obs)
        if not night:
            return None
        verified = verified_empty(base)
        pick = _night_pick(night, verified)
        if pick["people"] == 0 and _verified_name(pick) in verified:
            data = safe_image(base, _verified_name(pick))
            if data is not None:
                return data
        return safe_image(base, pick["_image"])
    if key in _SURV_KEYS:
        surv = load_surveillance(base)
        raw = next((surv[k] for k in _SURV_KEYS[key] if isinstance(surv.get(k), dict)), None)
        if raw is not None:
            return safe_image(base, str(raw.get("image") or raw.get("image_file") or ""))
    return None


def room_image(room_key: str, base: Path | None = None) -> bytes | None:
    """Último cuadro redactado en vivo de una sala conocida (lista blanca)."""
    base = base or witness_dir()
    if base is None:
        return None
    live = [o for o in load_observations(base) if o["is_live"] and o["room_key"] == room_key]
    return safe_image(base, live[-1]["_image"]) if live else None


def latest_image(base: Path | None = None) -> bytes | None:
    """Compatibilidad: el cuadro de ocupación más reciente."""
    return surveillance_image("occupancy", base)
