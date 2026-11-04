"""Detección explicable: reglas + línea base por actor + correlación entre apps.

La decisión de contener NUNCA depende solo del modelo. Muse Spark puede
hacer triage del incidente correlacionado (``triage_incident``, opcional y
apagado si no se pasa cliente), pero solo agrega una explicación: no sube
ni baja la severidad ni dispara la contención.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from shield.autopilot.events import SecurityEvent, cold_room_physics_verdict

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass
class ActorBaseline:
    median_amount: float = 0.0
    known_beneficiaries: set[str] = field(default_factory=set)
    usual_hours: set[int] = field(default_factory=set)
    scheduled_defrost_hours: set[int] = field(default_factory=set)

    @classmethod
    def from_events(cls, events: list[SecurityEvent]) -> ActorBaseline:
        amounts = [float(e.values["amount"]) for e in events if e.values.get("amount")]
        return cls(
            median_amount=float(statistics.median(amounts)) if amounts else 0.0,
            known_beneficiaries={str(e.values["beneficiary"]) for e in events
                                 if e.values.get("beneficiary")},
            usual_hours={e.ts.hour for e in events},
            scheduled_defrost_hours={e.ts.hour for e in events
                                     if e.action == "defrost" and e.values.get("scheduled")},
        )


@dataclass(frozen=True)
class Finding:
    kind: str
    severity: str  # low | medium | high | critical
    reason: str  # explicación legible, nunca "el modelo dijo"
    event_ids: tuple[str, ...] = ()
    apps: tuple[str, ...] = ()
    actors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "severity": self.severity, "reason": self.reason,
                "event_ids": list(self.event_ids), "apps": list(self.apps),
                "actors": list(self.actors)}


@dataclass(frozen=True)
class Incident:
    findings: tuple[Finding, ...]
    severity: str
    apps: tuple[str, ...]
    actors: tuple[str, ...]
    event_ids: tuple[str, ...]
    correlated: bool = False
    correlation_reasons: tuple[str, ...] = ()
    triage: str | None = None  # solo explicación opcional de Muse Spark

    def to_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "apps": list(self.apps),
                "actors": list(self.actors), "event_ids": list(self.event_ids),
                "correlated": self.correlated,
                "correlation_reasons": list(self.correlation_reasons),
                "triage": self.triage,
                "findings": [f.to_dict() for f in self.findings]}


def _odd_hour(event: SecurityEvent, base: ActorBaseline) -> bool:
    if event.ts.hour in (0, 1, 2, 3, 4):
        return True
    # Solo marca "fuera de su horario" con una línea base con variedad real.
    return len(base.usual_hours) >= 3 and event.ts.hour not in base.usual_hours


def detect(events: list[SecurityEvent],
           baseline: ActorBaseline | list[SecurityEvent] | None = None) -> list[Finding]:
    """Reglas explicables sobre eventos normalizados (ordenados por hora)."""
    evs = sorted(events, key=lambda e: e.ts)
    if isinstance(baseline, ActorBaseline):
        base = baseline
    elif baseline:
        base = ActorBaseline.from_events(list(baseline))
    else:
        base = ActorBaseline()  # sin historia: todo beneficiario es desconocido
    findings: list[Finding] = []

    def add(kind, severity, reason, hit):
        findings.append(Finding(kind, severity, reason, (hit.event_id,), (hit.app,), (hit.actor,)))

    for e in evs:
        if e.actor == "wairrior-autopilot":
            add("forged_autopilot_actor", "high",
                "actor auto-declarado 'wairrior-autopilot' en un evento "
                "entrante: canal no autenticado, sospechoso", e)
        amount = float(e.values.get("amount") or 0)
        atypical = base.median_amount > 0 and amount > base.median_amount * 3
        new_bene = bool(e.values.get("beneficiary")) and str(
            e.values["beneficiary"]) not in base.known_beneficiaries
        if e.app in ("payments", "pos_erp") and e.action in ("transfer", "supplier_change"):
            signals = [new_bene and "beneficiario nuevo", atypical and "monto atípico",
                       _odd_hour(e, base) and "horario raro"]
            hit_signals = [s for s in signals if s]
            if len(hit_signals) >= 2:
                add("payment_anomaly", "high",
                    f"{e.action} con {' + '.join(hit_signals)} (actor {e.actor})", e)
            elif hit_signals:
                add("payment_anomaly", "medium",
                    f"{e.action} con {hit_signals[0]} (actor {e.actor})", e)
        if e.app == "cold_room" and e.action == "defrost":
            duration = float(e.values.get("duration_min") or 0)
            off_schedule = not e.values.get("scheduled") and (
                not base.scheduled_defrost_hours
                or e.ts.hour not in base.scheduled_defrost_hours)
            if duration > 45 or off_schedule:
                add("defrost_anomaly", "high" if duration > 120 else "medium",
                    f"deshielo de {duration:g} min fuera de calendario o largo", e)
        if e.app == "cold_room":
            verdict = cold_room_physics_verdict(e)
            if verdict is not None and verdict.decision == "block":
                add("physics_block", "critical",
                    f"física (M1): {verdict.reason}", e)

    # Cambio de IBAN seguido de pago al mismo objetivo (ventana 24 h).
    ibans = [e for e in evs if e.action == "iban_change"]
    for pay in (e for e in evs if e.action == "transfer"):
        for iban in ibans:
            delta = pay.ts - iban.ts
            if iban.target == pay.target and timedelta(0) <= delta <= timedelta(hours=24):
                findings.append(Finding(
                    "iban_then_payment", "critical",
                    f"cambio de IBAN de {pay.target} seguido de pago en "
                    f"{(pay.ts - iban.ts).total_seconds() / 3600:.1f} h",
                    (iban.event_id, pay.event_id), (iban.app, pay.app), (pay.actor,)))

    # Ráfaga de llamadas de un token: >=10 en 60 s.
    by_token: dict[str, list[SecurityEvent]] = defaultdict(list)
    for e in evs:
        if e.token_id:
            by_token[e.token_id].append(e)
    for token, hits in by_token.items():
        for i, first in enumerate(hits):
            burst = [h for h in hits[i:] if (h.ts - first.ts) <= timedelta(seconds=60)]
            if len(burst) >= 10:
                findings.append(Finding(
                    "token_burst", "high",
                    f"ráfaga de {len(burst)} llamadas en 60 s del token {token}",
                    tuple(h.event_id for h in burst),
                    tuple(sorted({h.app for h in burst})), (first.actor,)))
                break
    return findings


def _campaign_keys(event: SecurityEvent) -> dict[str, set[str]]:
    """Claves de campaña de un evento: objetivo, beneficiario/IBAN, equipo, patrón."""
    keys: dict[str, set[str]] = {"target": set(), "beneficiary": set(),
                                "pattern": {"anomalous_write"}}
    if event.target:
        keys["target"].add(event.target)
    for name in ("beneficiary", "iban_last4", "iban", "supplier"):
        if event.values.get(name):
            keys["beneficiary"].add(str(event.values[name]))
    if event.app == "cold_room":
        keys["target"].add(f"equipment:{event.target}")
    return keys


def correlate(events: list[SecurityEvent], findings: list[Finding],
              *, window_min: float = 10.0) -> Incident:
    """Correlación por campaña en 24 h, no solo por actor en 10 min.

    Espaciar 90 min y rotar actores/tokens (C3-13) ya no evade: dos o más
    apps marcadas correlacionan si en 24 h comparten actor, token,
    OBJETIVO (mismo proveedor/equipo), beneficiario/IBAN o la firma de
    campaña (escrituras anómalas del mismo patrón). La ventana corta de
    ``window_min`` sigue correlacionando por sí sola.
    """
    evs = sorted(events, key=lambda e: e.ts)
    flagged_ids = {eid for f in findings for eid in f.event_ids}
    flagged = [e for e in evs if e.event_id in flagged_ids]
    reasons: list[str] = []
    if len({e.app for e in flagged}) >= 2 and flagged:
        span = flagged[-1].ts - flagged[0].ts
        if span <= timedelta(minutes=window_min):
            reasons.append(f"window_{window_min:g}m")
        if span <= timedelta(hours=24):
            if len({e.actor for e in flagged}) < len(flagged) or len(flagged) == 1:
                if len({e.actor for e in flagged}) == 1:
                    reasons.append("same_actor_24h")
            tokens = [e.token_id for e in flagged if e.token_id]
            if tokens and len(set(tokens)) < len(tokens):
                reasons.append("same_token_24h")
            for kind in ("target", "beneficiary", "pattern"):
                seen: set[str] = set()
                for e in flagged:
                    values = _campaign_keys(e)[kind]
                    if seen & values:
                        reasons.append(f"same_{kind}_24h")
                        break
                    seen |= values
    correlated = bool(reasons)
    severity = "low"
    for f in findings:
        if SEVERITY_ORDER[f.severity] > SEVERITY_ORDER[severity]:
            severity = f.severity
    if correlated:
        severity = "critical"
    return Incident(
        findings=tuple(findings), severity=severity if findings else "low",
        apps=tuple(sorted({e.app for e in flagged or evs})),
        actors=tuple(sorted({e.actor for e in flagged or evs})),
        event_ids=tuple(e.event_id for e in (flagged or evs)), correlated=correlated,
        correlation_reasons=tuple(dict.fromkeys(reasons)))


def triage_incident(incident: Incident,
                    spark: Callable[[Incident], str] | None = None) -> Incident:
    """Triage opcional con Muse Spark. Sin cliente: no-op. Nunca decide contención."""
    if spark is None:
        return incident
    from dataclasses import replace
    return replace(incident, triage=str(spark(incident))[:500])
