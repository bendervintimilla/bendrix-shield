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

from shield.autopilot.events import (
    ColdRoomHistory,
    SecurityEvent,
    cold_room_physics_verdict,
)

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
# Supuesto rotulado de calendario normal: hasta un ciclo de deshielo al
# día (<=60 min en 24 h por equipo). Sobre eso, aunque cada deshielo
# individual sea "programado" y corto, el patrón acumulado es anómalo.
NORMAL_DEFROST_MIN_PER_24H = 60.0

# Testigo físico (shield.witness): comandos físicos y orden de decisiones.
PHYSICAL_ACTIONS = frozenset({
    "set_setpoint", "setpoint", "defrost", "compressor_off",
    "door", "door_open", "open_door", "door_close", "door_unlock",
})
DECISION_ORDER = {"allow": 0, "ask_owner": 1, "block": 2}
WITNESS_MAX_AGE_S = 120.0
_WITNESS_SKEW_S = 2.0  # tolerancia de reloj cámara/comando


def harden_decision(decision: str, floor: str | None) -> str:
    """Endurece una decisión física con el piso del testigo. Nunca la relaja."""
    if floor is None:
        return decision
    if DECISION_ORDER.get(floor, 0) > DECISION_ORDER.get(decision, 0):
        return floor
    return decision


def _room_of(event: SecurityEvent) -> tuple[str, str]:
    site = str(event.values.get("site") or "").strip().casefold()
    room = str(event.values.get("room") or event.target or "").strip().casefold()
    return site, room


def witness_state(event: SecurityEvent, cameras: list[SecurityEvent], witness: Any = None,
                  *, max_age_s: float = WITNESS_MAX_AGE_S) -> dict[str, Any] | None:
    """Testimonio de la sala del comando en su instante. ``None`` = sala sin testigo.

    Fuentes: eventos ``camera`` de la misma tanda (``camera_event``) y/o un
    ``WitnessRegistry``. Stale (sin observación previa, vieja, futura o con
    error de SAM) => ``{"stale": True, "people": None}``: falla cerrado.
    """
    site, room = _room_of(event)
    if not room:
        return None
    same = [c for c in cameras if _room_of(c)[1] == room and (not site or _room_of(c)[0] == site)]
    if same:
        prior = [c for c in same
                 if (c.ts - event.ts).total_seconds() <= _WITNESS_SKEW_S]
        if not prior:
            return {"stale": True, "people": None, "camera": same[0].actor, "age_s": None}
        last = max(prior, key=lambda c: c.ts)
        age = (event.ts - last.ts).total_seconds()
        stale = age > max_age_s or not bool(last.values.get("ok", True))
        return {"stale": stale, "people": None if stale else int(last.values.get("people") or 0),
                "camera": last.actor, "age_s": round(age, 3)}
    if witness is not None and witness.watches(site, room):
        stale = witness.is_stale(site, room, event.ts, max_age_s)
        obs = witness.latest(site, room)
        return {"stale": stale,
                "people": None if stale or obs is None else int(obs.people),
                "camera": f"camera:{obs.camera}" if obs is not None else None,
                "age_s": None if obs is None else round(
                    (event.ts - obs.captured_dt()).total_seconds(), 3)}
    return None


def witness_findings(event: SecurityEvent, state: dict[str, Any] | None
                     ) -> tuple[list[Finding], str | None]:
    """Reglas del testigo para un comando físico -> (findings, piso de decisión)."""
    if state is None or event.app == "camera" or event.action not in PHYSICAL_ACTIONS:
        return [], None
    hit = ((event.event_id,), (event.app,), (event.actor,))
    remote = event.source != "on_site"
    stale = bool(state["stale"])
    people = state.get("people")
    where = event.values.get("room") or event.target
    if remote and (stale or people == 0):
        why = ("testigo de cámara sin dato fresco (falla cerrado)" if stale
               else "la cámara ve 0 personas en la sala")
        return [Finding("unattended_remote_physical_command", "high",
                        f"{event.action} remoto (source={event.source}) en {where}: {why}",
                        *hit)], "ask_owner"
    if not remote and not stale and people == 0:
        return [Finding("on_site_claim_contradicted", "critical",
                        f"{event.action} dice venir de personal en sitio pero la cámara "
                        f"ve 0 personas en {where}", *hit)], "block"
    if not remote and stale:
        return [Finding("on_site_claim_unverified", "high",
                        f"{event.action} dice venir de personal en sitio y el testigo de "
                        f"{where} no tiene dato fresco (falla cerrado)", *hit)], "ask_owner"
    return [], None


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
           baseline: ActorBaseline | list[SecurityEvent] | None = None,
           cold_history: ColdRoomHistory | None = None, witness: Any = None,
           *, witness_max_age_s: float = WITNESS_MAX_AGE_S) -> list[Finding]:
    """Reglas explicables sobre eventos normalizados (ordenados por hora).

    ``witness``: ``shield.witness.WitnessRegistry`` opcional; también cuentan
    los eventos ``camera`` de la tanda. Sin testigo para la sala, las
    reglas del testigo no aplican (comportamiento previo intacto).
    """
    evs = sorted(events, key=lambda e: e.ts)
    if isinstance(baseline, ActorBaseline):
        base = baseline
    elif baseline:
        base = ActorBaseline.from_events(list(baseline))
    else:
        base = ActorBaseline()  # sin historia: todo beneficiario es desconocido
    findings: list[Finding] = []
    tracker = cold_history if cold_history is not None else ColdRoomHistory()
    defrost_log: dict[str, list[tuple[Any, float]]] = {}
    cameras = [e for e in evs if e.app == "camera"]

    def add(kind, severity, reason, hit):
        findings.append(Finding(kind, severity, reason, (hit.event_id,), (hit.app,), (hit.actor,)))

    for e in evs:
        w_findings, w_floor = witness_findings(
            e, witness_state(e, cameras, witness, max_age_s=witness_max_age_s)
            if e.action in PHYSICAL_ACTIONS else None)
        findings.extend(w_findings)
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
            verdict = cold_room_physics_verdict(
                e, state=tracker.state_for(e.target),
                history=tracker.recent_actions(e.target, e.ts))
            if verdict is not None:
                # El testigo solo endurece: nunca relaja la decisión física.
                tracker.record(e, harden_decision(verdict.decision, w_floor))
                if verdict.decision == "block":
                    add("physics_block", "critical",
                        f"física (M1): {verdict.reason}", e)
        if e.app == "cold_room" and e.action == "defrost":
            # Patrón acumulado 24 h por equipo (deshielos lentos y bajos).
            past = [(ts, d) for ts, d in defrost_log.get(e.target, [])
                    if timedelta(0) <= e.ts - ts <= timedelta(hours=24)]
            total = sum(d for _, d in past) + float(e.values.get("duration_min") or 0)
            defrost_log[e.target] = [*past, (e.ts, float(e.values.get("duration_min") or 0))]
            if len(past) >= 1 and total > NORMAL_DEFROST_MIN_PER_24H:
                add("defrost_pattern", "high" if total > 120 else "medium",
                    f"deshielos repetidos en {e.target}: {total:g} min en 24 h "
                    f"sobre el calendario normal (<= {NORMAL_DEFROST_MIN_PER_24H:g} min)", e)

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
