"""Contención «contain first, ask later»: reversible automático, irreversible al dueño.

- low: solo registrar. medium: contención reversible por app (bloquear la
  acción, retener el pago, rotar el token, equipo a su último estado seguro,
  app en solo lectura). critical o >=2 apps: CIRCUIT BREAKER (congela
  escrituras en todas las apps, revoca tokens, equipos a estado seguro).
- Pagar o cambiar un IBAN de forma definitiva NUNCA se hace solo.
- Cada medida tiene ``undo``. El aviso al dueño se arma DESPUÉS de contener
  y no se envía de verdad: solo texto, o WhatsApp en sandbox/replay.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from shield.autopilot.detect import Incident
from shield.autopilot.events import SecurityEvent


class TokenOps(Protocol):
    """Rotación/revocación de tokens (en producción: shield.actions)."""

    def rotate(self, actor: str) -> str: ...
    def revoke(self, actor: str) -> None: ...
    def restore(self, actor: str) -> None: ...


class InMemoryTokenOps:
    """Implementación local determinista para tests y simulación."""

    def __init__(self) -> None:
        self.rotated: dict[str, str] = {}
        self.revoked: set[str] = set()

    def rotate(self, actor: str) -> str:
        new = f"tok_rotated_{uuid.uuid4().hex[:8]}"
        self.rotated[actor] = new
        self.revoked.discard(actor)
        return new

    def revoke(self, actor: str) -> None:
        self.revoked.add(actor)

    def restore(self, actor: str) -> None:
        self.revoked.discard(actor)


@dataclass
class Measure:
    kind: str  # log|block_action|hold_payment|rotate_token|revoke_tokens|
    #            safe_state|read_only|circuit_breaker|pending_owner
    app: str
    target: str
    reversible: bool = True
    undo_id: str = field(default_factory=lambda: f"undo_{uuid.uuid4().hex[:10]}")
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "app": self.app, "target": self.target,
                "reversible": self.reversible, "undo_id": self.undo_id,
                "detail": self.detail}


@dataclass
class ContainmentResult:
    severity: str
    circuit_breaker: bool
    measures: list[Measure] = field(default_factory=list)
    pending_owner: list[str] = field(default_factory=list)
    detect_to_contain_ms: float = 0.0
    notice_en: str = ""
    notice_es: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "circuit_breaker": self.circuit_breaker,
                "measures": [m.to_dict() for m in self.measures],
                "pending_owner": list(self.pending_owner),
                "detect_to_contain_ms": round(self.detect_to_contain_ms, 3),
                "notice_en": self.notice_en, "notice_es": self.notice_es}


class ContainmentEngine:
    """Estado de contención en memoria, con undo por medida."""

    def __init__(self, token_ops: TokenOps | None = None) -> None:
        self.tokens: TokenOps = token_ops or InMemoryTokenOps()
        self.read_only: set[str] = set()
        self.frozen: set[str] = set()  # circuit breaker: sin escrituras
        self.safe_states: dict[str, str] = {}
        self.held_payments: set[str] = set()
        self.blocked_actions: set[str] = set()
        self.log: list[str] = []
        self._undo: dict[str, Any] = {}

    def _apply(self, measure: Measure, undo) -> Measure:
        self._undo[measure.undo_id] = undo
        return measure

    def undo(self, undo_id: str) -> bool:
        undo = self._undo.pop(undo_id, None)
        if undo is None:
            return False
        undo()
        return True

    def undo_all(self, result: ContainmentResult) -> int:
        return sum(1 for m in reversed(result.measures) if self.undo(m.undo_id))

    # -- medidas ---------------------------------------------------------
    def block_action(self, event: SecurityEvent) -> Measure:
        self.blocked_actions.add(event.event_id)
        return self._apply(Measure("block_action", event.app, event.target,
                                   detail=event.action),
                           lambda: self.blocked_actions.discard(event.event_id))

    def hold_payment(self, event: SecurityEvent) -> Measure:
        self.held_payments.add(event.event_id)
        return self._apply(Measure("hold_payment", event.app, event.target,
                                   detail="pago retenido (hold), no ejecutado"),
                           lambda: self.held_payments.discard(event.event_id))

    def rotate_token(self, actor: str, app: str) -> Measure:
        new = self.tokens.rotate(actor)
        return self._apply(Measure("rotate_token", app, actor, detail=f"nuevo {new}"),
                           lambda: self.tokens.restore(actor))

    def revoke_tokens(self, actor: str, app: str) -> Measure:
        self.tokens.revoke(actor)
        return self._apply(Measure("revoke_tokens", app, actor),
                           lambda: self.tokens.restore(actor))

    def set_safe_state(self, app: str, target: str) -> Measure:
        previous = self.safe_states.get(target)
        self.safe_states[target] = "last_safe_state"
        def undo() -> None:
            if previous is None:
                self.safe_states.pop(target, None)
            else:
                self.safe_states[target] = previous
        return self._apply(Measure("safe_state", app, target,
                                   detail="equipo en su último estado seguro"), undo)

    def read_only_app(self, app: str) -> Measure:
        self.read_only.add(app)
        return self._apply(Measure("read_only", app, app),
                           lambda: self.read_only.discard(app))

    def circuit_breaker(self, apps: list[str]) -> Measure:
        self.frozen.update(apps)
        return self._apply(Measure("circuit_breaker", "*", ",".join(apps),
                                   detail="escrituras congeladas en todas las apps"),
                           lambda: [self.frozen.discard(a) for a in apps])


def build_owner_notice(result: ContainmentResult, *, lang: str = "en") -> str:
    """Texto para WhatsApp/correo DESPUÉS de contener. No envía nada."""
    done = [f"{m.kind} ({m.app}:{m.target})" for m in result.measures
            if m.kind not in ("log", "pending_owner")]
    pending = "; ".join(result.pending_owner)
    if lang == "es":
        text = ("Fuiste atacado. Ya hicimos: " + (", ".join(done) or "registrar el evento")
                + ". Toca para deshacer / liberar con tu segundo factor.")
        extra = f" Pendiente de tu decisión (nunca automático): {pending}." if pending else ""
        return text + extra
    text = ("You were attacked. We already did: " + (", ".join(done) or "logged the event")
            + ". Tap to undo / release with your second factor.")
    extra = f" Waiting for your decision (never automatic): {pending}." if pending else ""
    return text + extra


def respond(incident: Incident, events: list[SecurityEvent],
            engine: ContainmentEngine | None = None, *,
            started: float | None = None) -> ContainmentResult:
    """Aplica la política según severidad. ``started``: perf_counter de detección."""
    engine = engine or ContainmentEngine()
    t0 = started if started is not None else time.perf_counter()
    by_id = {e.event_id: e for e in events}
    flagged = [by_id[i] for i in incident.event_ids if i in by_id]
    result = ContainmentResult(severity=incident.severity, circuit_breaker=False)
    if not incident.findings or incident.severity == "low":
        engine.log.append(f"low: {[f.kind for f in incident.findings]}")
        result.measures.append(Measure("log", "*", "", detail="solo registrar"))
    elif incident.severity == "medium":
        for e in flagged:
            result.measures.append(engine.block_action(e))
            if e.app == "payments" and e.action == "transfer":
                result.measures.append(engine.hold_payment(e))
            if e.app == "cold_room":
                result.measures.append(engine.set_safe_state(e.app, e.target))
            result.measures.append(engine.read_only_app(e.app))
        for actor in incident.actors:
            result.measures.append(engine.rotate_token(actor, flagged[0].app if flagged else "*"))
    else:  # high: contención fuerte por app; critical / >=2 apps: circuit breaker
        breaker = incident.severity == "critical" or len(incident.apps) >= 2
        for e in flagged:
            result.measures.append(engine.block_action(e))
            if e.app == "payments" and e.action == "transfer":
                result.measures.append(engine.hold_payment(e))
            if e.app == "cold_room":
                result.measures.append(engine.set_safe_state(e.app, e.target))
        for actor in incident.actors:
            result.measures.append(
                engine.revoke_tokens(actor, "*") if breaker
                else engine.rotate_token(actor, flagged[0].app if flagged else "*"))
        if breaker:
            apps = sorted({e.app for e in events} | set(incident.apps))
            result.measures.append(engine.circuit_breaker(apps))
            result.circuit_breaker = True
    # Lo irreversible jamás es automático: queda para el dueño.
    for e in flagged:
        if e.action == "transfer":
            result.pending_owner.append(f"pagar a {e.target} (retenido, requiere tu OK)")
        if e.action == "iban_change":
            result.pending_owner.append(f"cambio definitivo de IBAN de {e.target} (requiere tu OK)")
    result.detect_to_contain_ms = (time.perf_counter() - t0) * 1000.0
    result.notice_en = build_owner_notice(result, lang="en")
    result.notice_es = build_owner_notice(result, lang="es")
    return result


def run_pipeline(events: list[SecurityEvent], baseline=None,
                 engine: ContainmentEngine | None = None, spark=None):
    """Detección → correlación → contención, midiendo detección→contención en ms."""
    from shield.autopilot.detect import correlate, detect, triage_incident
    started = time.perf_counter()
    findings = detect(events, baseline)
    incident = triage_incident(correlate(events, findings), spark)
    return incident, respond(incident, events, engine, started=started)


def dispatch_notice_sandbox(result: ContainmentResult, whatsapp: Any | None) -> dict[str, Any]:
    """Envía el aviso SOLO si el canal WhatsApp está en simulador (outbox local)."""
    if whatsapp is None:
        return {"sent": False, "mode": "text_only", "text": result.notice_en}
    if not getattr(whatsapp, "simulator_mode", False):
        return {"sent": False, "mode": "live_blocked", "text": result.notice_en}
    return {"sent": True, "mode": "sandbox",
            "result": whatsapp.send_text(result.notice_en), "text": result.notice_en}
