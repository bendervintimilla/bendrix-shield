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
- ``campaign``: una misma campaña en 2 apps (ej. IBAN en ERP +
  transferencia en pagos) congela el actor, el proveedor afectado y las
  transferencias a beneficiarios nuevos o cambiados en 24 h. Los pagos
  recurrentes a beneficiarios conocidos siguen: es UN flujo de fraude,
  no el negocio entero (eso fue lo que Arkéa no pudo hacer).
- ``global``: congela escrituras de agentes en todas las apps. SOLO si
  la correlación toca >=3 apps o hay compromiso de plataforma (varios
  actores). Aun ahí, las operaciones humanas recurrentes a
  beneficiarios conocidos siguen, con aviso. Justificación: solo una
  campaña que ya saltó por todo el negocio justifica pausar agentes.

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
from shield.autopilot.events import (
    SecurityEvent,
    cold_room_physics_verdict,
    emit_safe_state_rescue,
    verify_rescue,
)


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
        self.campaign_actors: set[str] = set()
        self.campaign_suppliers: set[str] = set()
        self.contained_actors: set[str] = set()
        self.contained_tokens: set[str] = set()
        self.safe_states: dict[str, str] = {}
        self.held_payments: set[str] = set()
        self.blocked_actions: set[str] = set()
        self.log: list[str] = []
        self.rescue_verdicts: list[Any] = []
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
        if self.global_breaker:
            # Aun en global: la operación humana recurrente a un
            # beneficiario conocido sigue (con aviso ya enviado).
            if event.source == "human":
                return event.app != "payments" or bool(
                    event.values.get("beneficiary_known"))
            return False
        if (event.app in ("cold_room", "payments") and event.source != "human"
                and (event.actor in self.contained_actors
                     or (event.token_id and event.token_id in self.contained_tokens))):
            # Actor/token contenido: TODA escritura física y de pagos
            # cae hasta liberación, cambie el target o la acción (C3-11/12).
            return False
        if event.actor in self.campaign_actors:
            # Actor de la campaña congelado: solo sobrevive su pago
            # recurrente a beneficiario conocido.
            return (event.app == "payments" and event.action == "transfer"
                    and bool(event.values.get("beneficiary_known")))
        if event.actor in self.revoked_actors:
            return False
        if (event.target in self.campaign_suppliers
                and event.action in ("transfer", "iban_change", "supplier_change")
                and not event.values.get("beneficiary_known")):
            return False
        if (self.campaign_suppliers and event.app == "payments"
                and event.action == "transfer"
                and not event.values.get("beneficiary_known")):
            return False  # beneficiarios nuevos/cambiados (24 h) congelados
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
        # Contención física con RescueGrant real de M1: el emisor firmado
        # emite la acción de último estado seguro y el gate la verifica
        # con grant (allow de rescate), no por el string requested_by.
        _action, grant = emit_safe_state_rescue(target or "camara")
        self.rescue_verdicts.append(verify_rescue(_action, grant))
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

    def freeze_campaign(self, actor: str, suppliers: list[str]) -> Measure:
        self.campaign_actors.add(actor)
        self.campaign_suppliers.update(suppliers)
        self.tokens.revoke(actor)
        def undo() -> None:
            self.campaign_actors.discard(actor)
            for s in suppliers:
                self.campaign_suppliers.discard(s)
            self.tokens.restore(actor)
        return self._apply(Measure("freeze_campaign", "*", actor,
                                   detail="actor, proveedor y beneficiarios nuevos"),
                           undo)

    def contain_actor_writes(self, actor: str, tokens: list[str]) -> Measure:
        self.contained_actors.add(actor)
        self.contained_tokens.update(tokens)
        def undo() -> None:
            self.contained_actors.discard(actor)
            for tok in tokens:
                self.contained_tokens.discard(tok)
        return self._apply(Measure("freeze_actor_writes", "*", actor,
                                   detail="toda escritura física y de pagos"),
                           undo)

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


def _pretty_supplier(target: str) -> str:
    name = target.split(":")[-1].replace("-", " ").strip()
    return name[:1].upper() + name[1:] if name else "the supplier"


def _fmt_amount(event: SecurityEvent) -> str:
    amount = event.values.get("amount")
    if amount is None:
        return ""
    value = float(amount)
    text = f"{value:,.0f}" if value == int(value) else f"{value:,.2f}"
    currency = event.values.get("currency")
    return f"{currency} {text}" if currency else text


def build_business_notice(incident: Incident | None, events: list[SecurityEvent],
                          result: ContainmentResult, *, lang: str = "en") -> str:
    """Aviso de negocio: máximo 7 líneas, sin ids ni nombres internos.

    Determinista: cada cifra sale de un evento marcado o del veredicto
    físico de ese evento. Nunca inventa montos, nombres ni temperaturas.
    """
    by_id = {e.event_id: e for e in events}
    flagged = sorted((by_id[i] for i in (incident.event_ids if incident else ())
                      if i in by_id), key=lambda e: e.ts)
    es = lang == "es"
    lines: list[str] = []
    if flagged:
        hhmm = flagged[0].ts.strftime("%H:%M")
        lines.append(f"wAIrrior detuvo un ataque a las {hhmm}." if es
                     else f"wAIrrior stopped an attack at {hhmm}.")
    else:
        lines.append("wAIrrior detuvo un ataque." if es else "wAIrrior stopped an attack.")
    kinds = {f.kind for f in incident.findings} if incident else set()
    seen_apps: set[str] = set()
    for e in flagged:
        if e.app in seen_apps:
            continue
        if e.app == "cold_room" and e.action == "defrost":
            seen_apps.add(e.app)
            verdict = cold_room_physics_verdict(e)
            peak = f"{round(verdict.peak_product_c, 1):g}" if verdict else "?"
            dur = float(e.values.get("duration_min") or 0)
            when = f"{dur / 60:g} horas" if es and dur >= 60 else (
                f"{dur / 60:g}-hour" if dur >= 60 else f"{dur:g} min")
            lines.append(
                f"Cámara de frío: un deshielo de {when} habría dañado tu stock "
                f"(producto a {peak} °C); quedó en su último estado seguro a 3 °C."
                if es else
                f"Cold room: a {when} defrost would have spoiled your stock "
                f"(product to {peak} °C); we kept it at its last safe setting, 3 °C.")
        elif e.app == "payments" and e.action == "transfer":
            seen_apps.add(e.app)
            amount = _fmt_amount(e)
            supplier = _pretty_supplier(e.target)
            amt = f" de {amount}" if es and amount else (f" of {amount}" if amount else "")
            lines.append(
                f"Pagos: un pago{amt} a un IBAN nuevo para {supplier} está retenido; "
                f"los datos bancarios de {supplier} están congelados." if es else
                f"Payments: a payment{amt} to a new IBAN for {supplier} is on hold; "
                f"{supplier}'s bank details are frozen.")
        elif e.app == "pos_erp" and "payments" not in {x.app for x in flagged}:
            seen_apps.add(e.app)
            supplier = _pretty_supplier(e.target)
            lines.append(
                f"Proveedores: los datos bancarios de {supplier} están congelados."
                if es else
                f"Suppliers: {supplier}'s bank details are frozen.")
        elif e.app == "ai_gateway" and ("token_burst" in kinds or len(flagged) >= 3):
            seen_apps.add(e.app)
            lines.append(
                "Una llave de un agente de IA fue robada; ya la reemplazamos."
                if es else
                "One AI agent's key was stolen; we replaced it.")
    if result.scope_level == "global":
        lines.append(
            "Las demás escrituras de agentes están en pausa; tus pagos humanos "
            "habituales a proveedores conocidos siguen." if es else
            "Other agent writes are paused; your usual human payments to "
            "known suppliers keep working.")
    elif result.scope_level != "none":
        lines.append("Todo lo demás sigue funcionando." if es
                     else "Everything else keeps working.")
    has_iban = any("IBAN" in item for item in result.pending_owner)
    if has_iban:
        lines.append(
            "Toca para deshacer · Aprueba el cambio de IBAN solo con tu "
            "segundo factor." if es else
            "Tap to undo · Approve the IBAN change only with your second factor.")
    elif result.pending_owner:
        lines.append(
            "Toca para deshacer · Aprobar el pago requiere tu segundo factor."
            if es else
            "Tap to undo · Approving the payment needs your second factor.")
    else:
        lines.append("Toca para deshacer." if es else "Tap to undo.")
    return "\n".join(lines[:7])


def build_owner_notice(result: ContainmentResult, *, lang: str = "en") -> str:
    """Compatibilidad: aviso de negocio sin contexto de incidente."""
    return build_business_notice(None, [], result, lang=lang)


def respond(incident: Incident, events: list[SecurityEvent],
            engine: ContainmentEngine | None = None, *,
            started: float | None = None) -> ContainmentResult:
    """Aplica la política por niveles. ``started``: perf_counter de detección."""
    engine = engine or ContainmentEngine()
    t0 = started if started is not None else time.perf_counter()
    by_id = {e.event_id: e for e in events}
    flagged = [by_id[i] for i in incident.event_ids if i in by_id]
    # Global solo con >=3 apps o compromiso de plataforma: varios actores
    # Y el gateway comprometido (ráfaga de tokens), no dos agentes sueltos.
    platform = bool(incident.correlated and len(incident.actors) >= 2
                    and "ai_gateway" in incident.apps
                    and any(f.kind == "token_burst" for f in incident.findings))
    if not incident.findings or incident.severity == "low":
        level = "none"
    elif incident.correlated and (len(incident.apps) >= 3 or platform):
        level = "global"
    elif incident.correlated and len(incident.apps) >= 2:
        level = "campaign"  # una campaña en 2 apps no es el negocio entero
    elif incident.severity in ("high", "critical"):
        level = "app"
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
        suppliers = sorted({e.target for e in flagged if e.target})
        for actor in incident.actors:
            if level == "global":
                result.measures.append(engine.revoke_tokens(actor, "*"))
            elif level == "campaign":
                result.measures.append(engine.freeze_campaign(actor, suppliers))
                result.frozen_scopes.append(f"campaign:actor:{actor}")
            else:
                result.measures.append(
                    engine.rotate_token(actor, flagged[0].app if flagged else "*"))
        tokens_by_actor: dict[str, list[str]] = {}
        for e in flagged:
            if e.token_id:
                tokens_by_actor.setdefault(e.actor, []).append(e.token_id)
        for actor in incident.actors:
            result.measures.append(engine.contain_actor_writes(
                actor, tokens_by_actor.get(actor, [])))
        if level == "campaign":
            result.frozen_scopes.append("payments:transfer:new_or_changed_24h")
            result.frozen_scopes.extend(f"campaign:supplier:{s}" for s in suppliers)
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
    result.notice_en = build_business_notice(incident, events, result, lang="en")
    result.notice_es = build_business_notice(incident, events, result, lang="es")
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
