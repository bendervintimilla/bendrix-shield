"""Última observación del testigo por (site, room), con caducidad que falla cerrado.

Testigo stale (sin observación, observación vieja, del futuro respecto
del momento evaluado o con error de SAM) = no hay testimonio: ``presence``
devuelve ``None`` y las reglas del autopiloto lo tratan como sospechoso.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from shield.witness.observe import WitnessObservation

DEFAULT_MAX_AGE_S = 120.0


def _key(site: str, room: str) -> tuple[str, str]:
    return (str(site or "").strip().casefold(), str(room or "").strip().casefold())


def _now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    return now if now.tzinfo else now.replace(tzinfo=UTC)


class WitnessRegistry:
    """Guarda la última observación por sala. Seguro entre hilos, sin red."""

    def __init__(self) -> None:
        self._latest: dict[tuple[str, str], WitnessObservation] = {}
        self._watched: set[tuple[str, str]] = set()
        self._lock = threading.Lock()

    def register(self, site: str, room: str) -> None:
        """Declara que esa sala tiene testigo aunque aún no haya observación."""
        with self._lock:
            self._watched.add(_key(site, room))

    def update(self, obs: WitnessObservation) -> None:
        """Guarda ``obs`` si es más nueva que la vigente (sin bytes de imagen)."""
        from dataclasses import replace

        key = _key(obs.site, obs.room)
        light = replace(obs, redacted_image=None)
        with self._lock:
            self._watched.add(key)
            current = self._latest.get(key)
            if current is None or current.captured_dt() <= light.captured_dt():
                self._latest[key] = light

    def _resolve(self, site: str, room: str) -> tuple[str, str] | None:
        key = _key(site, room)
        if key in self._watched:
            return key
        if not key[0]:  # sin site: vale si la sala es única entre sitios
            hits = [k for k in self._watched if k[1] == key[1]]
            if len(hits) == 1:
                return hits[0]
        return None

    def watches(self, site: str, room: str) -> bool:
        with self._lock:
            return self._resolve(site, room) is not None

    def latest(self, site: str, room: str) -> WitnessObservation | None:
        with self._lock:
            key = self._resolve(site, room)
            return self._latest.get(key) if key else None

    def age_s(self, site: str, room: str, now: datetime | None = None) -> float | None:
        obs = self.latest(site, room)
        if obs is None:
            return None
        return (_now(now) - obs.captured_dt()).total_seconds()

    def is_stale(self, site: str, room: str, now: datetime | None = None,
                 max_age_s: float = DEFAULT_MAX_AGE_S) -> bool:
        obs = self.latest(site, room)
        if obs is None or not obs.ok:
            return True
        age = (_now(now) - obs.captured_dt()).total_seconds()
        return age > max_age_s or age < -max_age_s

    def presence(self, site: str, room: str, now: datetime | None = None,
                 max_age_s: float = DEFAULT_MAX_AGE_S) -> int | None:
        """Personas vistas, o ``None`` si el testigo está stale."""
        if self.is_stale(site, room, now, max_age_s):
            return None
        obs = self.latest(site, room)
        return None if obs is None else int(obs.people)


_DEFAULT = WitnessRegistry()


def default_registry() -> WitnessRegistry:
    return _DEFAULT


def record(obs: WitnessObservation) -> None:
    _DEFAULT.update(obs)


def is_stale(site: str, room: str, now: datetime | None = None,
             max_age_s: float = DEFAULT_MAX_AGE_S) -> bool:
    return _DEFAULT.is_stale(site, room, now, max_age_s)


def presence(site: str, room: str, now: datetime | None = None,
             max_age_s: float = DEFAULT_MAX_AGE_S) -> int | None:
    return _DEFAULT.presence(site, room, now, max_age_s)
