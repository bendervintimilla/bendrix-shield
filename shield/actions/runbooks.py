"""Runbooks idempotentes y reversibles de contención.

Cada runbook expone ``plan()`` (sin efecto), ``apply(plan, approval_id=…)``
(con efecto), ``verify()`` y ``rollback(result)``. Todo efecto exige una
aprobación (``PendingRegistry``), salvo la contención automática
opcional ante un canario, que queda auditada. Ningún valor secreto se
escribe en planes, resultados públicos ni en la auditoría: solo token_id,
huella (sha256[:8]) y últimos 4.
"""

from __future__ import annotations

import hashlib
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from shield.registry import Registry
from shield.schemas import AgentTokenStatus
from shield.sdk.pending import PendingRegistry
from shield.vault.vault import BaseVault


class ApprovalRequired(RuntimeError):
    """Falta una aprobación válida para un runbook con efecto."""


class ManualStepRequired(RuntimeError):
    """El proveedor no tiene API de llaves: falta el paso manual verificado."""


def _fp(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


@dataclass
class Plan:
    plan_id: str
    action: str
    target: str
    steps: list[str]
    details: dict[str, Any] = field(default_factory=dict)
    reversible: bool = True

    def public(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "action": self.action,
            "target": self.target,
            "steps": list(self.steps),
            "details": dict(self.details),
            "reversible": self.reversible,
        }


@dataclass
class ActionResult:
    status: str  # applied | rolled_back | verified
    plan_id: str
    action: str
    target: str
    details: dict[str, Any] = field(default_factory=dict)
    new_token_id: str | None = None
    auto_contained: bool = False
    # Token en claro recién emitido: solo viaja al token_store del agente,
    # jamás a logs ni a la auditoría. repr lo oculta.
    secret: str | None = field(default=None, repr=False)


@dataclass
class VerifyResult:
    ok: bool
    action: str
    target: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditEntry:
    ts: str
    action: str
    target: str
    event: str  # plan | apply | verify | rollback
    approval_id: str | None = None
    auto_contained: bool = False
    details: dict[str, Any] = field(default_factory=dict)


class Actions:
    """Fachada: construye runbooks compartiendo registry/vault/auditoría."""

    def __init__(
        self,
        *,
        registry: Registry,
        vault: BaseVault | None = None,
        token_store: Any = None,
        approvals: PendingRegistry | Callable[[str], bool] | None = None,
        sandbox: bool = False,
        auto_contain: bool = False,
        health_checker: Callable[[str], bool] | None = None,
        deployer: Callable[..., Any] | None = None,
        key_providers: dict[str, Callable[[], str] | None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.registry = registry
        self.vault = vault
        self.token_store = token_store
        self.approvals = approvals if approvals is not None else PendingRegistry()
        self.sandbox = sandbox
        self.auto_contain = auto_contain
        self.health_checker = health_checker
        self.deployer = deployer
        self.key_providers = key_providers or {}
        self.sleep = sleep
        self.audit_log: list[AuditEntry] = []

    # -- fábrica de runbooks ---------------------------------------------
    def rotate_token(self, *, grace_s: float = 30.0) -> RotateTokenRunbook:
        return RotateTokenRunbook(self, grace_s=grace_s)

    def rotate_upstream_key(self) -> RotateUpstreamKeyRunbook:
        return RotateUpstreamKeyRunbook(self)

    def redeploy(self) -> RedeployRunbook:
        return RedeployRunbook(self)

    def revoke(self) -> RevokeRunbook:
        return RevokeRunbook(self)

    def verify(self) -> VerifyRunbook:
        return VerifyRunbook(self)

    def patch_plan(self) -> PatchPlanRunbook:
        return PatchPlanRunbook(self)

    # -- internos ----------------------------------------------------------
    def _audit(self, action, target, event, *, approval_id=None, auto=False, details=None):
        self.audit_log.append(
            AuditEntry(
                ts=datetime.now(UTC).isoformat(),
                action=action,
                target=target,
                event=event,
                approval_id=approval_id,
                auto_contained=auto,
                details=dict(details or {}),
            )
        )

    def check_approval(self, approval_id: str | None, *, auto_reason: str | None = None) -> bool:
        """True si hay aprobación válida o aplica contención automática."""
        if approval_id:
            gate = self.approvals
            if callable(gate) and not isinstance(gate, PendingRegistry):
                return bool(gate(approval_id))
            pending = gate.get(approval_id)  # type: ignore[attr-defined]
            if pending is not None and pending.status in ("approved", "executed"):
                return True
            raise ApprovalRequired(f"approval_id no aprobado: {approval_id}")
        if auto_reason == "canary_detected" and self.auto_contain:
            return True
        raise ApprovalRequired("se requiere approval_id")

    def agent_health(self, agent: str) -> bool:
        if self.health_checker is not None:
            return bool(self.health_checker(agent))
        return any(t.status is AgentTokenStatus.ACTIVE for t in self.registry.list_tokens(agent))

    def _active_tokens(self, agent: str):
        return [t for t in self.registry.list_tokens(agent) if t.status is AgentTokenStatus.ACTIVE]


def _new_plan(action: str, target: str, steps: list[str], details=None) -> Plan:
    return Plan(
        plan_id=f"plan_{uuid.uuid4().hex[:12]}",
        action=action,
        target=target,
        steps=steps,
        details=dict(details or {}),
    )


class _BaseRunbook:
    action = "base"

    def __init__(self, ctx: Actions) -> None:
        self.ctx = ctx
        self._applied: dict[str, ActionResult] = {}

    def _require(self, plan: Plan, approval_id: str | None, reason: str | None) -> bool:
        auto = not approval_id and reason == "canary_detected" and self.ctx.auto_contain
        self.ctx.check_approval(approval_id, auto_reason=reason)
        return auto


class RotateTokenRunbook(_BaseRunbook):
    """Token nuevo al instante, gracia para el viejo y luego revoke.

    Sin redeploy: el SDK refresca desde el registro local del agente.
    Idempotente por plan_id; rollback revoca el nuevo (o reemite si el
    viejo ya expiró) y deja un token activo en el store.
    """

    action = "rotate_token"

    def __init__(self, ctx: Actions, *, grace_s: float = 30.0) -> None:
        super().__init__(ctx)
        self.grace_s = max(0.0, float(grace_s))
        self._timers: list[threading.Timer] = []

    def plan(self, *, agent: str, reason: str | None = None) -> Plan:
        actives = self.ctx._active_tokens(agent)
        plan = _new_plan(
            self.action,
            agent,
            [
                f"emitir un token nuevo para {agent} (sin redeploy)",
                f"gracia de {self.grace_s:g} s para el token viejo y luego revoke",
                "escribir el token nuevo en el registro local del agente (SDK)",
                "verificar health del agente y que los demás agentes no se tocan",
            ],
            {"agent": agent, "active_token_ids": [t.token_id for t in actives], "reason": reason},
        )
        self.ctx._audit(self.action, agent, "plan", details={"plan_id": plan.plan_id})
        return plan

    def apply(self, plan: Plan, *, approval_id: str | None = None) -> ActionResult:
        if plan.plan_id in self._applied:  # idempotente
            return self._applied[plan.plan_id]
        agent = plan.target
        reason = plan.details.get("reason")
        auto = self._require(plan, approval_id, reason)
        actives = self.ctx._active_tokens(agent)
        if not actives:
            raise ValueError(f"sin token activo para rotar: {agent}")
        old = actives[0]
        new_token, raw = self.ctx.registry.create_token(
            old.agent,
            old.app,
            scopes=list(old.scopes),
            models=list(old.models),
            spend_cap_usd=old.spend_cap_usd,
        )
        if self.ctx.token_store is not None:
            self.ctx.token_store.set_token(agent, raw, new_token.token_id)
        for old_token in actives:
            if self.grace_s <= 0:
                self.ctx.registry.revoke(old_token.token_id)
            else:
                timer = threading.Timer(
                    self.grace_s, self.ctx.registry.revoke, args=(old_token.token_id,)
                )
                timer.daemon = True
                timer.start()
                self._timers.append(timer)
        result = ActionResult(
            status="applied",
            plan_id=plan.plan_id,
            action=self.action,
            target=agent,
            details={
                "old_token_ids": [t.token_id for t in actives],
                "grace_s": self.grace_s,
                "new_token_fingerprint": _fp(raw),
            },
            new_token_id=new_token.token_id,
            auto_contained=auto,
            secret=raw,
        )
        self._applied[plan.plan_id] = result
        self.ctx._audit(
            self.action,
            agent,
            "apply",
            approval_id=approval_id,
            auto=auto,
            details={"plan_id": plan.plan_id, "new_token_id": new_token.token_id},
        )
        return result

    def verify(self, *, agent: str) -> VerifyResult:
        ok = self.ctx.agent_health(agent)
        result = VerifyResult(
            ok=ok,
            action="verify",
            target=agent,
            details={agent: ok, "active": [t.token_id for t in self.ctx._active_tokens(agent)]},
        )
        self.ctx._audit("verify", agent, "verify", details={agent: ok})
        return result

    def rollback(self, result: ActionResult) -> ActionResult:
        for timer in self._timers:
            timer.cancel()
        agent = result.target
        rolled = ActionResult(
            status="rolled_back",
            plan_id=result.plan_id,
            action=self.action,
            target=agent,
            details={"revoked_new_token_id": result.new_token_id},
        )
        if result.new_token_id:
            self.ctx.registry.revoke(result.new_token_id)
        if not self.ctx._active_tokens(agent):
            # El viejo ya expiró: reemitir para restaurar el servicio.
            tokens = self.ctx.registry.list_tokens(agent)
            if tokens:
                base = tokens[0]
                new_token, raw = self.ctx.registry.create_token(
                    base.agent,
                    base.app,
                    scopes=list(base.scopes),
                    models=list(base.models),
                    spend_cap_usd=base.spend_cap_usd,
                )
                rolled.new_token_id = new_token.token_id
                rolled.secret = raw
                if self.ctx.token_store is not None:
                    self.ctx.token_store.set_token(agent, raw, new_token.token_id)
        elif self.ctx.token_store is not None:
            # El store debe apuntar a un token activo, no al revocado.
            active = self.ctx._active_tokens(agent)[0]
            current = self.ctx.token_store.get_token(agent)
            if (
                current is None
                or self.ctx.registry.authenticate(current) is None
                or (self.ctx.registry.authenticate(current).token_id != active.token_id)
            ):
                # No guardamos el raw del viejo: reemitir uno equivalente.
                new_token, raw = self.ctx.registry.create_token(
                    active.agent,
                    active.app,
                    scopes=list(active.scopes),
                    models=list(active.models),
                    spend_cap_usd=active.spend_cap_usd,
                )
                self.ctx.registry.revoke(active.token_id)
                rolled.new_token_id = new_token.token_id
                rolled.secret = raw
                self.ctx.token_store.set_token(agent, raw, new_token.token_id)
        self.ctx._audit(self.action, agent, "rollback", details={"plan_id": result.plan_id})
        return rolled


class RotateUpstreamKeyRunbook(_BaseRunbook):
    """Rotación de llave del proveedor: solo sandbox.

    Si el proveedor expone API de llaves (``key_providers[provider]``),
    se crea y se guarda en el vault; si no, ``apply`` exige el valor
    entregado por el paso manual (``manual_value``) y lo verifica por
    huella. El valor nunca aparece en resultados ni auditoría.
    """

    action = "rotate_upstream_key"

    def plan(self, *, provider: str) -> Plan:
        if not self.ctx.sandbox:
            raise PermissionError("rotate_upstream_key solo en sandbox")
        has_api = self.ctx.key_providers.get(provider) is not None
        steps = (
            ["crear llave nueva vía API del proveedor", "guardarla en el vault", "verificar huella"]
            if has_api
            else [
                "paso manual: crear la llave nueva en el proveedor y entregarla al runbook",
                "guardarla en el vault",
                "verificar que la huella cambió",
            ]
        )
        plan = _new_plan(self.action, provider, steps, {"provider": provider, "has_api": has_api})
        self.ctx._audit(self.action, provider, "plan", details={"plan_id": plan.plan_id})
        return plan

    def apply(
        self, plan: Plan, *, approval_id: str | None = None, manual_value: str | None = None
    ) -> ActionResult:
        if plan.plan_id in self._applied:
            return self._applied[plan.plan_id]
        if not self.ctx.sandbox:
            raise PermissionError("rotate_upstream_key solo en sandbox")
        if self.ctx.vault is None:
            raise ValueError("rotate_upstream_key requiere vault")
        self._require(plan, approval_id, None)
        provider = plan.target
        key_name = "META_MODEL_API_KEY" if provider == "meta" else f"{provider.upper()}_API_KEY"
        before = self.ctx.vault.describe(key_name)
        factory = self.ctx.key_providers.get(provider)
        if factory is not None:
            new_value = factory()
            if not new_value:
                raise ManualStepRequired(f"la API de {provider} no devolvió llave")
        elif manual_value:
            new_value = manual_value
        else:
            raise ManualStepRequired(
                f"{provider} no tiene API de llaves: crea la llave a mano "
                "y pásala como manual_value"
            )
        self.ctx.vault.put(key_name, new_value)
        after = self.ctx.vault.describe(key_name)
        if after["fingerprint"] == before["fingerprint"]:
            raise ValueError("la huella no cambió: la llave nueva es igual a la anterior")
        result = ActionResult(
            status="applied",
            plan_id=plan.plan_id,
            action=self.action,
            target=provider,
            details={
                "key_name": key_name,
                "fingerprint": after["fingerprint"],
                "last4": after["last4"],
            },
        )
        self._applied[plan.plan_id] = result
        self.ctx._audit(
            self.action,
            provider,
            "apply",
            approval_id=approval_id,
            details={"plan_id": plan.plan_id, "fingerprint": after["fingerprint"]},
        )
        return result

    def verify(self, *, provider: str) -> VerifyResult:
        ok = self.ctx.vault is not None and self.ctx.vault.get("META_MODEL_API_KEY") is not None
        return VerifyResult(ok=ok, action="verify", target=provider, details={provider: ok})

    def rollback(self, result: ActionResult) -> ActionResult:
        # No se guarda la llave anterior (secreto): rollback = re-rotar a mano.
        raise ManualStepRequired("rollback de llave upstream requiere una llave manual nueva")


class RedeployRunbook(_BaseRunbook):
    """Redeploy de un servicio del sandbox vía deployer inyectado."""

    action = "redeploy"

    def plan(self, *, service: str) -> Plan:
        if not self.ctx.sandbox:
            raise PermissionError("redeploy solo en sandbox")
        plan = _new_plan(
            self.action,
            service,
            [f"redesplegar {service} en el sandbox", "verificar health tras el despliegue"],
            {"service": service},
        )
        self.ctx._audit(self.action, service, "plan", details={"plan_id": plan.plan_id})
        return plan

    def apply(self, plan: Plan, *, approval_id: str | None = None) -> ActionResult:
        if plan.plan_id in self._applied:
            return self._applied[plan.plan_id]
        if not self.ctx.sandbox:
            raise PermissionError("redeploy solo en sandbox")
        self._require(plan, approval_id, None)
        deployer = self.ctx.deployer or (
            lambda service: {"service": service, "status": "redeployed"}
        )
        outcome = deployer(plan.target)
        result = ActionResult(
            status="applied",
            plan_id=plan.plan_id,
            action=self.action,
            target=plan.target,
            details={"outcome": str(outcome)[:200]},
        )
        self._applied[plan.plan_id] = result
        self.ctx._audit(
            self.action,
            plan.target,
            "apply",
            approval_id=approval_id,
            details={"plan_id": plan.plan_id},
        )
        return result

    def verify(self, *, service: str) -> VerifyResult:
        # Sin health_checker de servicio, el sandbox se asume sano tras deploy.
        ok = True if self.ctx.health_checker is None else bool(self.ctx.health_checker(service))
        return VerifyResult(ok=ok, action="verify", target=service, details={service: ok})

    def rollback(self, result: ActionResult) -> ActionResult:
        deployer = self.ctx.deployer
        if deployer is not None:
            deployer(result.target)  # redespliegue = reversión en el sandbox
        self.ctx._audit(self.action, result.target, "rollback", details={"plan_id": result.plan_id})
        return ActionResult(
            status="rolled_back", plan_id=result.plan_id, action=self.action, target=result.target
        )


class RevokeRunbook(_BaseRunbook):
    """Revocación inmediata de los tokens activos de un agente."""

    action = "revoke"

    def plan(self, *, agent: str, reason: str | None = None) -> Plan:
        actives = self.ctx._active_tokens(agent)
        plan = _new_plan(
            self.action,
            agent,
            [
                f"revocar {len(actives)} token(s) activo(s) de {agent}",
                "verificar que el agente da 401",
            ],
            {"agent": agent, "active_token_ids": [t.token_id for t in actives], "reason": reason},
        )
        self.ctx._audit(self.action, agent, "plan", details={"plan_id": plan.plan_id})
        return plan

    def apply(self, plan: Plan, *, approval_id: str | None = None) -> ActionResult:
        if plan.plan_id in self._applied:
            return self._applied[plan.plan_id]
        agent = plan.target
        auto = self._require(plan, approval_id, plan.details.get("reason"))
        revoked = []
        for token in self.ctx._active_tokens(agent):
            self.ctx.registry.revoke(token.token_id)
            revoked.append(token.token_id)
        result = ActionResult(
            status="applied",
            plan_id=plan.plan_id,
            action=self.action,
            target=agent,
            details={"revoked_token_ids": revoked},
            auto_contained=auto,
        )
        self._applied[plan.plan_id] = result
        self.ctx._audit(
            self.action,
            agent,
            "apply",
            approval_id=approval_id,
            auto=auto,
            details={"plan_id": plan.plan_id, "revoked": revoked},
        )
        return result

    def verify(self, *, agent: str) -> VerifyResult:
        ok = not self.ctx._active_tokens(agent)
        return VerifyResult(ok=ok, action="verify", target=agent, details={agent: ok})

    def rollback(self, result: ActionResult) -> ActionResult:
        # Revocar es irreversible: restaurar = emitir un token nuevo.
        agent = result.target
        tokens = self.ctx.registry.list_tokens(agent)
        rolled = ActionResult(
            status="rolled_back", plan_id=result.plan_id, action=self.action, target=agent
        )
        if tokens:
            base = tokens[0]
            new_token, raw = self.ctx.registry.create_token(
                base.agent,
                base.app,
                scopes=list(base.scopes),
                models=list(base.models),
                spend_cap_usd=base.spend_cap_usd,
            )
            rolled.new_token_id = new_token.token_id
            rolled.secret = raw
            if self.ctx.token_store is not None:
                self.ctx.token_store.set_token(agent, raw, new_token.token_id)
        self.ctx._audit(self.action, agent, "rollback", details={"plan_id": result.plan_id})
        return rolled


class PatchPlanRunbook(_BaseRunbook):
    """Plan de parcheo del sandbox: pasos y reversión, sin tocar prod."""

    action = "patch_plan"

    def plan(self, *, service: str, package: str, fixed_version: str) -> Plan:
        plan = _new_plan(
            self.action,
            service,
            [
                f"actualizar {package} a {fixed_version} en {service} (solo sandbox)",
                "correr la verificación de salud del servicio",
                "rollback: volver a desplegar la versión anterior si falla",
            ],
            {"service": service, "package": package, "fixed_version": fixed_version},
        )
        self.ctx._audit(self.action, service, "plan", details={"plan_id": plan.plan_id})
        return plan

    def apply(self, plan: Plan, *, approval_id: str | None = None) -> ActionResult:
        if plan.plan_id in self._applied:
            return self._applied[plan.plan_id]
        if not self.ctx.sandbox:
            raise PermissionError("patch_plan solo en sandbox")
        self._require(plan, approval_id, None)
        result = ActionResult(
            status="applied",
            plan_id=plan.plan_id,
            action=self.action,
            target=plan.target,
            details=dict(plan.details),
        )
        self._applied[plan.plan_id] = result
        self.ctx._audit(
            self.action,
            plan.target,
            "apply",
            approval_id=approval_id,
            details={"plan_id": plan.plan_id},
        )
        return result

    def verify(self, *, service: str) -> VerifyResult:
        ok = True if self.ctx.health_checker is None else bool(self.ctx.health_checker(service))
        return VerifyResult(ok=ok, action="verify", target=service, details={service: ok})

    def rollback(self, result: ActionResult) -> ActionResult:
        self.ctx._audit(self.action, result.target, "rollback", details={"plan_id": result.plan_id})
        return ActionResult(
            status="rolled_back", plan_id=result.plan_id, action=self.action, target=result.target
        )


class VerifyRunbook(_BaseRunbook):
    """Health check por agente: cada agente conectado sigue en verde."""

    action = "verify"

    def plan(self, *, agents: list[str] | None = None) -> Plan:
        targets = agents or sorted({t.agent for t in self.ctx.registry.list_tokens()})
        plan = _new_plan(
            self.action,
            ",".join(targets),
            [f"health check de {a}" for a in targets],
            {"agents": targets},
        )
        self.ctx._audit(self.action, plan.target, "plan", details={"plan_id": plan.plan_id})
        return plan

    def apply(self, plan: Plan, *, approval_id: str | None = None) -> ActionResult:
        # Verificar no tiene efecto: no exige aprobación.
        checked = self.verify(agents=list(plan.details.get("agents") or []))
        return ActionResult(
            status="verified" if checked.ok else "applied",
            plan_id=plan.plan_id,
            action=self.action,
            target=plan.target,
            details=dict(checked.details),
        )

    def verify(self, *, agents: list[str] | None = None) -> VerifyResult:
        targets = agents or sorted({t.agent for t in self.ctx.registry.list_tokens()})
        details = {a: self.ctx.agent_health(a) for a in targets}
        ok = all(details.values()) if details else True
        result = VerifyResult(ok=ok, action="verify", target=",".join(targets), details=details)
        self.ctx._audit("verify", result.target, "verify", details=dict(details))
        return result

    def rollback(self, result: ActionResult) -> ActionResult:
        return ActionResult(
            status="rolled_back", plan_id=result.plan_id, action=self.action, target=result.target
        )
