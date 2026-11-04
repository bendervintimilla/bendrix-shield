"""Contención «contain first, ask later» con circuit breaker en 3 niveles.

Justificación de cada nivel (el daño colateral manda):

- ``actor`` (token/agente): revoca o rota SOLO el token de ese agente y
  bloquea sus acciones marcadas. Justificación: un token robado es un
  problema de identidad, no del negocio; los demás agentes y apps siguen.
- ``app``: congela solo las escrituras de ESA app y de ESE tipo de
  operación (ej. ``payments:transfer:new_beneficiary``; un pago a un
  beneficiario conocido no es ese tipo). Justificación: un crítico en una
  sola app (un deshielo forzado) no puede congelar pagos ni el gateway;
  el resto de operaciones de la misma app tampoco, si no son del tipo
  atacado.
- ``global``: congela escrituras en todas las apps conectadas y revoca
  los tokens de la campaña. SOLO si hay correlación del mismo
  actor/token/campaña en >=2 apps (``Incident.correlated``). Justificación:
  ahí el atacante ya saltó de app; contener por partes deja la campaña
  viva. Es el equivalente al «suspender todo» de Arkéa, pero acotado a
  las apps conectadas, con lecturas vivas y undo del dueño.

Lo irreversible (pagar, IBAN definitivo) nunca es automático. Cada medida
tiene ``undo``. El aviso se arma DESPUÉS de contener; no se envía de
verdad (texto o WhatsApp solo en sandbox/replay).
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


class ShieldActionsTokenOps:
    """TokenOps real sobre ``shield.actions`` + Registry del gateway.

    Usa la contención automática auditada de los runbooks
    (``auto_contain`` + reason ``canary_detected``): rotar/revocar sin
    esperar al dueño, como pide Mauro. ``restore`` emite un token nuevo
    equivalente (revocar es irreversible; restaurar = reemitir).
    """

    def __init__(self, actions: Any) -> None:
        self.actions = actions
        self._revoked_results: dict[str, Any] = {}

    def rotate(self, actor: str) -> str:
        runbook = self.actions.rotate_token(grace_s=0)
        plan = runbook.plan(agent=actor, reason="canary_detected")
        result = runbook.apply(plan)
        return result.new_token_id or ""

    def revoke(self, actor: str) -> None:
        runbook = self.actions.revoke()
        plan = runbook.plan(agent=actor, reason="canary_detected")
        self._revoked_results[actor] = (runbook, runbook.apply(plan))

    def restore(self, actor: str) -> None:
        entry = self._revoked_results.pop(actor, None)
        if entry is not None:
            runbook, result = entry
            runbook.rollback(result)


def operation_scope(event: SecurityEvent) -> str:
    """Tipo de operación congelable a nivel app (app + operación, no app entera)."""
    if event.app == "payments" and event.action == "transfer":
        known = bool(event.values.get("beneficiary_known"))
        return "transfer:known_beneficiary" if known else "transfer:new_beneficiary"
    if event.app == "cold_room":
        return f"{event.action}:{event.target}"
    if event.app == "ai_gateway":
        return f"{event.action}:{event.actor}"
    return f"{event.action}:{event.target}"


@dataclass
class Measure:
    kind: str  # log|block_action|hold_payment|rotate_token|revoke_tokens|
    #            safe_state|freeze_app_scope|circuit_breaker
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
    scope_level: str = "none"  # none | actor | app | global
    frozen_scopes: list[str] = field(default_factory=list)
    measures: list[Measure] = field(default_factory=list)
    pending_owner: list[str] = field(default_factory=list)
    detect_to_contain_ms: float = 0.0
    notice_en: str = ""
    notice_es: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "circuit_breaker": self.circuit_breaker,
                "scope_level": self.scope_level,
                "frozen_scopes": list(self.frozen_scopes),
                "measures": [m.to_dict() for m in self.measures],
                "pending_owner": list(self.pending_owner),
                "detect_to_contain_ms": round(self.detect_to_contain_ms, 3),
                "notice_en": self.notice_en, "notice_es": self.notice_es}


class ContainmentEngine:
    """Estado de contención en memoria, con undo por medida."""

    def __init__(self, token_ops: TokenOps | None = None) -> None:
        self.tokens: TokenOps = token_ops or InMemoryTokenOps()
        self.read_only: set[str] = set()
        self.frozen: set[str] = set()  # alias: apps bajo circuit breaker global
        self.frozen_scopes: set[tuple[str, str]] = set()  # (app, operación)
        self.global_breaker: bool = False
        self.revoked_actors: set[str] = set()
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

    def allows_write(self, event: SecurityEvent) -> bool:
        """¿Esta escritura legítima seguiría funcionando tras la contención?"""
        if event.event_id in self.blocked_actions or event.event_id in self.held_payments:
            return False
        if event.actor in self.revoked_actors:
            return False
        if self.global_breaker:
            return False
        return (event.app, operation_scope(event)) not in self.frozen_scopes

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
        self.revoked_actors.add(actor)
        def undo() -> None:
            self.tokens.restore(actor)
            self.revoked_actors.discard(actor)
        return self._apply(Measure("revoke_tokens", app, actor), undo)

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

    def freeze_app_scope(self, event: SecurityEvent) -> Measure:
        key = (event.app, operation_scope(event))
        self.frozen_scopes.add(key)
        return self._apply(
            Measure("freeze_app_scope", event.app, key[1],
                    detail="solo este tipo de operación en esta app"),
            lambda: self.frozen_scopes.discard(key))

    def circuit_breaker(self, apps: list[str]) -> Measure:
        self.frozen.update(apps)
        self.global_breaker = True
        def undo() -> None:
            for a in apps:
                self.frozen.discard(a)
            self.global_breaker = bool(self.frozen)
        return self._apply(Measure("circuit_breaker", "*", ",".join(apps),
                                   detail="escrituras congeladas en todas las apps"),
                           undo)


def build_owner_notice(result: ContainmentResult, *, lang: str = "en") -> str:
    """Texto para WhatsApp/correo DESPUÉS de contener. No envía nada."""
    done = list(dict.fromkeys(
        f"{m.kind} ({m.app}:{m.target})" for m in result.measures
        if m.kind not in ("log", "pending_owner")))
    pending = "; ".join(result.pending_owner)
    if lang == "es":
        text = ("Fuiste atacado. Ya hicimos: " + (", ".join(done) or "registrar el evento")
                + f" [alcance: {result.scope_level}]."
                + " Toca para deshacer / liberar con tu segundo factor.")
        extra = f" Pendiente de tu decisión (nunca automático): {pending}." if pending else ""
        return text + extra
    text = ("You were attacked. We already did: " + (", ".join(done) or "logged the event")
            + f" [scope: {result.scope_level}]."
            + " Tap to undo / release with your second factor.")
    extra = f" Waiting for your decision (never automatic): {pending}." if pending else ""
    return text + extra


def respond(incident: Incident, events: list[SecurityEvent],
            engine: ContainmentEngine | None = None, *,
            started: float | None = None) -> ContainmentResult:
    """Aplica la política por niveles. ``started``: perf_counter de detección."""
    engine = engine or ContainmentEngine()
    t0 = started if started is not None else time.perf_counter()
    by_id = {e.event_id: e for e in events}
    flagged = [by_id[i] for i in incident.event_ids if i in by_id]
    global_scope = bool(incident.correlated and len(incident.apps) >= 2)
    if not incident.findings or incident.severity == "low":
        level = "none"
    elif global_scope:
        level = "global"
    elif incident.severity in ("high", "critical"):
        level = "app"  # crítico en una sola app: jamás congela las demás
    else:
        level = "actor"
    result = ContainmentResult(severity=incident.severity,
                               circuit_breaker=level == "global", scope_level=level)
    if level == "none":
        engine.log.append(f"low: {[f.kind for f in incident.findings]}")
        result.measures.append(Measure("log", "*", "", detail="solo registrar"))
    else:
        for e in flagged:
            result.measures.append(engine.block_action(e))
            if e.app == "payments" and e.action == "transfer":
                result.measures.append(engine.hold_payment(e))
            if e.app == "cold_room":
                result.measures.append(engine.set_safe_state(e.app, e.target))
            if level == "app":
                measure = engine.freeze_app_scope(e)
                result.measures.append(measure)
                result.frozen_scopes.append(f"{e.app}:{measure.target}")
        for actor in incident.actors:
            if level == "global":
                result.measures.append(engine.revoke_tokens(actor, "*"))
            else:  # actor/app: rotar (el agente legítimo sigue con token nuevo)
                result.measures.append(
                    engine.rotate_token(actor, flagged[0].app if flagged else "*"))
        if level == "global":
            apps = sorted({e.app for e in events} | set(incident.apps))
            result.measures.append(engine.circuit_breaker(apps))
    for e in flagged:
        if e.action == "transfer":
            result.pending_owner.append(f"pagar a {e.target} (retenido, requiere tu OK)")
        if e.action == "iban_change":
            result.pending_owner.append(
                f"cambio definitivo de IBAN de {e.target} (requiere tu OK)")
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
