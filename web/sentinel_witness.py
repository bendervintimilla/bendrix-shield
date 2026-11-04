"""Testigo de cámara real para la escena «Sentinel».

Lee lo que deja ``shield/witness`` (rama fx/w1-witness) en ``SHIELD_WITNESS_DIR``:

- ``observations.json``: lista de observaciones en el formato de
  ``WitnessObservation.public()`` (o ``{"observations": [...]}``).
- ``latest.jpg``: el último cuadro YA REDACTADO (personas cubiertas por
  siluetas con ``redact(...)``). Esta capa nunca ve la imagen cruda.

Si no hay carpeta, archivo o datos válidos, la escena sigue como siempre:
sin tarjeta con foto (placeholder neutro) y sin frase del testigo.
Nada de rutas privadas sale al navegador: solo campos públicos en lista
blanca.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

WITNESS_DIR_ENV = "SHIELD_WITNESS_DIR"
OBS_FILE = "observations.json"
IMAGE_FILE = "latest.jpg"
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_OBS_BYTES = 2 * 1024 * 1024
DEFAULT_SITE = "Clara del Rey, Madrid"
PLAYBACK_SOURCES = {"playback", "recorded", "replay", "recording"}
LIVE_SOURCES = {"live", "live_capture", "camera"}

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
    return text if len(text) <= 12 else text[:10] + "…"


def _camera_label(camera: str, es: bool) -> str:
    name = camera.replace("_", " ").replace("-", " ").strip()
    if not name:
        return "Cámara" if es else "Camera"
    low = name.lower()
    if es:
        known = {"kitchen": "cocina", "cocina": "cocina"}
        word = known.get(low)
        if word:
            return f"Cámara de {word}"
        return name[:1].upper() + name[1:]
    if "cam" in low:
        return name[:1].upper() + name[1:]
    word = "kitchen" if low == "cocina" else name
    return f"{word[:1].upper()}{word[1:]} camera"


def public_observation(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normaliza una observación pública; ``None`` si no sirve para la escena."""
    if not isinstance(raw, dict):
        return None
    ts = _parse_ts(raw.get("captured_at"))
    people = raw.get("people")
    if ts is None or isinstance(people, bool) or not isinstance(people, int) or people < 0:
        return None
    source = str(raw.get("source") or "").strip().lower()
    door = raw.get("door_open")
    response_ids = raw.get("response_ids") or []
    if isinstance(response_ids, str):
        response_ids = [response_ids]
    camera = str(raw.get("camera") or "").strip()[:60]
    return {
        "camera": camera,
        "camera_en": _camera_label(camera, False),
        "camera_es": _camera_label(camera, True),
        "site": str(raw.get("site") or DEFAULT_SITE).strip()[:80],
        "room": str(raw.get("room") or "").strip()[:60],
        "captured_at": ts.isoformat(),
        "captured_hhmm": ts.strftime("%H:%M"),
        "captured_date": ts.strftime("%Y-%m-%d"),
        "people": people,
        "door_open": door if isinstance(door, bool) else None,
        "model": str(raw.get("model") or "").strip()[:40],
        "response_id_short": _short_id(response_ids[0]) if response_ids else "",
        "latency_ms": _num(raw.get("latency_ms")),
        "cost_usd": _num(raw.get("cost_usd")),
        "source": source,
        "is_live": source in LIVE_SOURCES,
        "is_playback": source in PLAYBACK_SOURCES,
        "_ts": ts,
    }


def load_observations(base: Path | None = None) -> list[dict[str, Any]]:
    """Observaciones públicas válidas, de la más vieja a la más nueva."""
    base = base or witness_dir()
    if base is None:
        return []
    path = base / OBS_FILE
    try:
        if not path.is_file() or path.stat().st_size > MAX_OBS_BYTES:
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(data, dict):
        data = data.get("observations", [data] if "captured_at" in data else [])
    if not isinstance(data, list):
        return []
    out = [o for o in (public_observation(r) for r in data) if o is not None]
    out.sort(key=lambda o: o["_ts"])
    return out


def night_playback(observations: list[dict[str, Any]]) -> dict[str, Any] | None:
    """La grabación nocturna (00:00–05:59, hora del sitio) con 0 personas."""
    hits = [
        o for o in observations
        if o["is_playback"] and o["people"] == 0 and o["_ts"].hour < 6
    ]
    return hits[-1] if hits else None


def latest_image(base: Path | None = None) -> bytes | None:
    """Último cuadro redactado (JPEG) o ``None``. Nunca sigue rutas del cliente."""
    base = base or witness_dir()
    if base is None:
        return None
    path = base / IMAGE_FILE
    try:
        if path.is_symlink() or not path.is_file():
            return None
        if path.stat().st_size > MAX_IMAGE_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    return data if data[:3] == b"\xff\xd8\xff" else None


def strip_private(obs: dict[str, Any] | None) -> dict[str, Any] | None:
    if obs is None:
        return None
    return {k: v for k, v in obs.items() if not k.startswith("_")}


def witness_state() -> dict[str, Any]:
    """Lo que la escena muestra del testigo (sin rutas ni bytes)."""
    base = witness_dir()
    observations = load_observations(base)
    latest = observations[-1] if observations else None
    return {
        "available": latest is not None,
        "has_image": latest_image(base) is not None,
        "latest": strip_private(latest),
        "night": strip_private(night_playback(observations)),
    }


def night_finding(night: dict[str, Any] | None, lang: str) -> str:
    """Frase del frío con el dato del testigo; vacía si no hay grabación nocturna."""
    if not night:
        return ""
    hhmm = night["captured_hhmm"]
    if lang == "es":
        return (f"{night['camera_es']} (real, {hhmm}): 0 personas en el local — "
                "un deshielo remoto sin nadie allí")
    return (f"{night['camera_en']} (real, {hhmm}): 0 people on site — "
            "a remote defrost with nobody there")
