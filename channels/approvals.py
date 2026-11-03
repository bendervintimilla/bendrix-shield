"""Broker de aprobaciones del dueño: un solo camino para WhatsApp, voz y panel.

El broker crea la solicitud en el ``PendingRegistry`` de. El
``approval_id`` que consumen los runbooks de es ese ``pending_id``:
ningún canal inventa su propio id. Aprobar deja el pending en
``approved`` (válido para ``Actions.check_approval``); rechazar lo deja
en ``rejected`` y ningún efecto puede ejecutarse con él.
"""

from __future__ import annotations

import hmac
import time
from dataclasses import dataclass, field
from typing import Any

from shield.schemas import Decision, PolicyDecision
from shield.sdk.pending import PendingRegistry


class ApprovalRejected(ValueError):
    """La decisión no se acepta: nonce incorrecto, caducada o ya resuelta."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class ApprovalRequest:
    approval_id: str
    plan: dict[str, Any]
    status: str = "pending"  # pending | approved | rejected | expired
    approved_steps: list[list[str]] = field(default_factory=list)
    excluded_targets: list[str] = field(default_factory=list)
    # Reto de un solo uso que acompaña la decisión del dueño (lo emite el broker al
    # abrir la solicitud y lo lleva la superficie del dueño: panel, botón, flujo de voz).
    nonce: str = field(default="", repr=False)
    expires_at: float = 0.0

    def public(self) -> dict[str, Any]:
        # El nonce no viaja en la vista pública; el panel del dueño lo toma del broker.
        return {
            "approval_id": self.approval_id,
            "plan": self.plan,
            "status": self.status,
            "approved_steps": [list(s) for s in self.approved_steps],
            "excluded_targets": list(self.excluded_targets),
            "expires_at": self.expires_at,
        }


def _matches(target: str, names: list[str]) -> bool:
    low = target.lower()
    return any(name and name.lower() in low for name in names)


class ApprovalBroker:
    """Registra planes, recibe la decisión del dueño y filtra pasos."""

    def __init__(self, registry: PendingRegistry | None = None) -> None:
        self.registry = registry or PendingRegistry()
        self.requests: dict[str, ApprovalRequest] = {}

    def request(self, plan: dict[str, Any]) -> ApprovalRequest:
        summary = str(plan.get("summary") or "plan del guardián")
        pending = self.registry.add(
            agent="guardian",
            tool="guardian_plan",
            args={"plan": plan},
            decision=PolicyDecision(
                decision=Decision.ASK_OWNER,
                reason=summary,
                evidence=["channel:ask_owner"],
            ),
        )
        req = ApprovalRequest(
            approval_id=pending.pending_id,
            plan=plan,
            nonce=pending.nonce,
            expires_at=pending.expires_at,
        )
        self.requests[req.approval_id] = req
        return req

    def _check_decision(self, req: ApprovalRequest, nonce: str | None) -> None:
        """Una decisión vale solo si está pendiente, vigente y trae el nonce de esta solicitud."""
        if req.status != "pending":
            raise ApprovalRejected(
                "not_pending", f"aprobación {req.approval_id} no está pendiente: {req.status}"
            )
        if time.time() >= req.expires_at:
            req.status = "expired"
            self._sync_pending(req, "expired")
            raise ApprovalRejected("expired", f"aprobación {req.approval_id} caducada")
        if not nonce or not hmac.compare_digest(str(nonce), req.nonce):
            raise ApprovalRejected(
                "nonce_invalid", f"aprobación {req.approval_id}: nonce ausente o de otra solicitud"
            )

    def get(self, approval_id: str) -> ApprovalRequest | None:
        return self.requests.get(approval_id)

    def list_pending(self) -> list[ApprovalRequest]:
        return [r for r in self.requests.values() if r.status == "pending"]

    def _sync_pending(self, req: ApprovalRequest, status: str) -> None:
        pending = self.registry.get(req.approval_id)
        if pending is not None:
            pending.status = status
            if status == "approved":
                # La aprobación solo cubre los pasos aprobados, y cada uno una vez.
                pending.scope = {(a, t) for a, t in req.approved_steps}
            persist = getattr(self.registry, "_persist", None)
            if callable(persist):
                persist()

    def approve(
        self,
        approval_id: str,
        *,
        nonce: str | None,
        exclude_targets: list[str] | tuple[str, ...] = (),
        only_targets: list[str] | tuple[str, ...] | None = None,
    ) -> ApprovalRequest:
        req = self.requests[approval_id]
        self._check_decision(req, nonce)
        excluded = [str(t) for t in exclude_targets]
        approved: list[list[str]] = []
        for step in req.plan.get("steps") or []:
            if not step.get("requires_approval", True):
                continue
            target = str(step.get("target", ""))
            if excluded and _matches(target, excluded):
                continue
            if only_targets is not None and not _matches(target, [str(t) for t in only_targets]):
                continue
            approved.append([str(step.get("action", "")), target])
        req.approved_steps = approved
        req.excluded_targets = excluded
        req.status = "approved"
        self._sync_pending(req, "approved")
        return req

    def reject(self, approval_id: str, *, nonce: str | None = None) -> ApprovalRequest:
        # Rechazar siempre es seguro: no exige nonce, solo que siga pendiente.
        req = self.requests[approval_id]
        if req.status != "pending":
            raise ValueError(f"aprobación {approval_id} no está pendiente: {req.status}")
        req.status = "rejected"
        req.approved_steps = []
        self._sync_pending(req, "rejected")
        return req

    def is_approved(self, approval_id: str | None) -> bool:
        req = self.requests.get(approval_id or "")
        return bool(req and req.status == "approved" and time.time() < req.expires_at)

    def is_rejected(self, approval_id: str | None) -> bool:
        req = self.requests.get(approval_id or "")
        return bool(req and req.status == "rejected")

    def approved_steps_for(self, approval_id: str | None) -> set[tuple[str, str]]:
        req = self.requests.get(approval_id or "")
        if not req or req.status != "approved" or time.time() >= req.expires_at:
            return set()
        return {(a, t) for a, t in req.approved_steps}


class ChannelApprover:
    """``Approver`` asíncrono para el guardián: registra y espera al canal.

    ``ask_owner`` no bloquea: devuelve ``None`` y deja
    ``pending_approval_id`` para que WhatsApp/panel/voz resuelvan. El
    guardián retoma con ``tool_resume_approval`` + ``execute_approved``.
    """

    def __init__(self, broker: ApprovalBroker) -> None:
        self.broker = broker
        self.pending_approval_id: str | None = None
        self.asked: list[Any] = []

    def ask_owner(self, plan: Any) -> str | None:
        plan_dict = plan.to_dict() if hasattr(plan, "to_dict") else dict(plan)
        req = self.broker.request(plan_dict)
        self.pending_approval_id = req.approval_id
        self.asked.append(plan)
        return None

    def is_approved(self, approval_id: str | None) -> bool:
        return self.broker.is_approved(approval_id)

    def is_rejected(self, approval_id: str | None) -> bool:
        return self.broker.is_rejected(approval_id)

    def approved_steps_for(self, approval_id: str | None) -> set[tuple[str, str]]:
        return self.broker.approved_steps_for(approval_id)
