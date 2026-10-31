"""Acciones pendientes de aprobación del dueño (los canales las consumen)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shield.schemas import PolicyDecision


@dataclass
class PendingAction:
    pending_id: str
    agent: str
    tool: str
    args: dict[str, Any]
    decision: PolicyDecision
    status: str = "pending"  # pending | approved | rejected | executed
    _fn: Callable[..., Any] | None = field(default=None, repr=False)

    def public(self) -> dict[str, Any]:
        return {
            "pending_id": self.pending_id,
            "agent": self.agent,
            "tool": self.tool,
            "args": self.args,
            "decision": self.decision.model_dump(mode="json"),
            "status": self.status,
        }


class PendingRegistry:
    """Registro en memoria con espejo JSON opcional para el canal."""

    def __init__(self, store_path: Path | str | None = None) -> None:
        self._items: dict[str, PendingAction] = {}
        self.store_path = Path(store_path) if store_path else None

    def _persist(self) -> None:
        if self.store_path:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            data = [p.public() for p in self._items.values()]
            self.store_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(
        self,
        *,
        agent: str,
        tool: str,
        args: dict[str, Any],
        decision: PolicyDecision,
        fn: Callable[..., Any] | None = None,
    ) -> PendingAction:
        pending = PendingAction(
            pending_id=f"pend_{uuid.uuid4().hex[:12]}",
            agent=agent,
            tool=tool,
            args=args,
            decision=decision,
            _fn=fn,
        )
        self._items[pending.pending_id] = pending
        self._persist()
        return pending

    def get(self, pending_id: str) -> PendingAction | None:
        return self._items.get(pending_id)

    def list_pending(self) -> list[PendingAction]:
        return [p for p in self._items.values() if p.status == "pending"]

    def approve(self, pending_id: str) -> Any:
        pending = self._items[pending_id]
        if pending.status != "pending":
            raise ValueError(f"pending {pending_id} no está pendiente: {pending.status}")
        pending.status = "approved"
        result = pending._fn(**pending.args) if pending._fn else None
        pending.status = "executed"
        self._persist()
        return result

    def reject(self, pending_id: str) -> PendingAction:
        pending = self._items[pending_id]
        pending.status = "rejected"
        self._persist()
        return pending


default_registry = PendingRegistry()


class PolicyBlocked(RuntimeError):
    def __init__(self, decision: PolicyDecision) -> None:
        super().__init__(f"policy block: {decision.reason}")
        self.decision = decision


class PolicyPending(RuntimeError):
    def __init__(self, pending: PendingAction) -> None:
        super().__init__(
            f"policy ask_owner: pendiente {pending.pending_id}: {pending.decision.reason}"
        )
        self.pending = pending
        self.pending_id = pending.pending_id
        self.decision = pending.decision
