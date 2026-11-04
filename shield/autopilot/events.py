"""Formato común ``SecurityEvent`` y adaptadores por app.

Webhook para una app nueva (documentación operativa):

    POST /autopilot/webhook   (la app emisora lo adapta a su transporte)
    Content-Type: application/json

    {
      "app": "payments", "actor": "agent:payments-bot", "action": "transfer",
      "target": "supplier:acme", "source": "agent",
      "ts": "2026-11-04T10:00:00+00:00", "token_id": "tok_123",
      "values": {"amount": 1200.0, "currency": "USD", "beneficiary": "ES12..."}
    }

Basta con mandar ese JSON: ``SecurityEvent.from_dict`` lo valida y el resto
(detección, correlación, contención) no conoce la app de origen. Ningún
valor secreto debe ir en ``values``: solo ids, últimos 4 o huellas.
Todo determinista, sin red.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

APPS = ("ai_gateway", "payments", "pos_erp", "cold_room")


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if value:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)


@dataclass(frozen=True)
class SecurityEvent:
    """Evento normalizado: quién hizo qué, dónde, con qué valores y cuándo."""

    app: str
    actor: str
    action: str
    target: str = ""
    values: dict[str, Any] = field(default_factory=dict)
    source: str = "agent"  # agent | document | voice | schedule | human | attacker
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))
    token_id: str | None = None
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id, "app": self.app, "actor": self.actor,
            "action": self.action, "target": self.target,
            "values": dict(self.values), "source": self.source,
            "ts": self.ts.isoformat(), "token_id": self.token_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SecurityEvent:
        if not data.get("app") or not data.get("actor") or not data.get("action"):
            raise ValueError("SecurityEvent requiere app, actor y action")
        return cls(
            app=str(data["app"]), actor=str(data["actor"]), action=str(data["action"]),
            target=str(data.get("target") or ""), values=dict(data.get("values") or {}),
            source=str(data.get("source") or "agent"), ts=_parse_ts(data.get("ts")),
            token_id=data.get("token_id"),
            event_id=str(data.get("event_id") or f"evt_{uuid.uuid4().hex[:12]}"),
        )


# Adaptador genérico para el webhook descrito arriba.
def from_webhook(payload: dict[str, Any]) -> SecurityEvent:
    return SecurityEvent.from_dict(payload)


def from_gateway_call(log: Any) -> SecurityEvent:
    """Registro ya existente del gateway de IA (``CallLog`` o dict)."""
    get = (lambda k, d=None: log.get(k, d)) if isinstance(log, dict) else (
        lambda k, d=None: getattr(log, k, d))
    return SecurityEvent(
        app="ai_gateway", actor=str(get("agent", "unknown")), action="model_call",
        target=str(get("model", "")), source="agent",
        ts=_parse_ts(get("ts")), token_id=get("token_id"),
        values={"cost_usd": get("cost_usd", 0), "decision": str(get("decision", "allow")),
                "src_country": get("src_country"), "model": get("model")},
    )


def from_payment(raw: dict[str, Any]) -> SecurityEvent:
    """Pagos/banco: ``transfer`` | ``beneficiary_new`` | ``iban_change``."""
    action = str(raw.get("action") or "transfer")
    return SecurityEvent(
        app="payments", actor=str(raw.get("actor") or "unknown"), action=action,
        target=str(raw.get("target") or raw.get("supplier") or ""),
        source=str(raw.get("source") or "agent"), ts=_parse_ts(raw.get("ts")),
        token_id=raw.get("token_id"),
        values={k: raw.get(k) for k in
                ("amount", "currency", "beneficiary", "iban_last4", "supplier")
                if raw.get(k) is not None},
    )


def from_pos_erp(raw: dict[str, Any]) -> SecurityEvent:
    """POS/ERP: cambio de datos de proveedor u otra escritura sensible."""
    return SecurityEvent(
        app="pos_erp", actor=str(raw.get("actor") or "unknown"),
        action=str(raw.get("action") or "supplier_change"),
        target=str(raw.get("target") or raw.get("supplier") or ""),
        source=str(raw.get("source") or "agent"), ts=_parse_ts(raw.get("ts")),
        token_id=raw.get("token_id"),
        values={k: raw.get(k) for k in
                ("supplier", "field", "old_last4", "iban_last4", "amount")
                if raw.get(k) is not None},
    )


def from_cold_room(raw: dict[str, Any]) -> SecurityEvent:
    """Cámara de frío: ``set_setpoint`` | ``defrost`` | ``compressor_off`` | ``door_open``."""
    return SecurityEvent(
        app="cold_room", actor=str(raw.get("actor") or "refrigeracion"),
        action=str(raw.get("action") or raw.get("kind") or "set_setpoint"),
        target=str(raw.get("target") or raw.get("equipment") or "camara"),
        source=str(raw.get("source") or "agent"), ts=_parse_ts(raw.get("ts")),
        token_id=raw.get("token_id"),
        values={k: raw.get(k) for k in
                ("value", "duration_min", "scheduled", "equipment") if raw.get(k) is not None},
    )


def cold_room_physics_verdict(event: SecurityEvent) -> Any | None:
    """Pasa un evento de frío por ``shield.physics.gate`` (M1). None si no aplica."""
    if event.app != "cold_room":
        return None
    kind_map = {"set_setpoint": "set_setpoint", "defrost": "defrost",
                "compressor_off": "compressor_off", "door_open": "door_open"}
    kind = kind_map.get(event.action)
    if kind is None:
        return None
    from shield.physics.contract import ColdRoomParams, ProposedAction, RoomState
    from shield.physics.gate import verify_action

    action = ProposedAction(
        kind=kind, equipment=event.target or "camara",
        value=event.values.get("value"), duration_min=float(event.values.get("duration_min") or 0),
        requested_by=event.actor, source=event.source)
    return verify_action(ColdRoomParams(), RoomState(), action)
