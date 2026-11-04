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
from datetime import UTC, datetime, timedelta
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


def proposed_action_from_event(event: SecurityEvent) -> Any:
    """Acción física desde un evento ENTRANTE, sin privilegio alguno.

    El ``requested_by`` es solo una declaración: el gate de M1 ya no da
    privilegio por ese string; exige un RescueGrant firmado válido. Un
    evento con ``actor='wairrior-autopilot'`` queda marcado sospechoso
    en la evidencia del gate y en ``detect`` (C3-16), nunca rescatado.
    """
    from shield.physics.contract import ProposedAction

    return ProposedAction(
        kind=event.action, equipment=event.target or "camara",
        value=event.values.get("value"),
        duration_min=float(event.values.get("duration_min") or 0),
        requested_by=event.actor, source=event.source)


def emit_safe_state_rescue(target: str = "camara", state: Any | None = None):
    """Emisor REAL del rescate: ``issue_last_safe_action`` de M1.

    Devuelve ``(action, RescueGrant)`` firmado (HMAC, 60 s, un solo
    uso). Es la única vía por la que el autopiloto obtiene privilegio
    de rescate; ningún evento entrante pasa por aquí.
    """
    from shield.physics.contract import ColdRoomParams, RoomState
    from shield.physics.rescue import issue_last_safe_action

    params = ColdRoomParams(name=target or "camara")
    return issue_last_safe_action(params, state or RoomState())


def build_internal_rescue_action(equipment: str = "camara", value: float = 3.0) -> Any:
    """Compatibilidad: la acción del rescate interno (con su grant emitido)."""
    action, _grant = emit_safe_state_rescue(equipment)
    return action


def verify_rescue(action: Any, grant: Any, *, state: Any | None = None,
                  history: list | None = None) -> Any:
    """Verifica el rescate ante ``gate.verify_action(..., rescue_grant=...)``."""
    from shield.physics.contract import ColdRoomParams, RoomState
    from shield.physics.gate import verify_action

    params = ColdRoomParams(name=action.equipment)
    return verify_action(params, state or RoomState(), action,
                         history=history, rescue_grant=grant)


class ColdRoomHistory:
    """Estado e historia por equipo (24 h) para el veredicto físico.

    Sin esto, cada evento partía de un RoomState fresco: deshielos
    «lentos y bajos» repetidos nunca se acumulaban. Guarda el último
    estado conocido por equipo y las acciones ACEPTADAS recientes
    (las bloqueadas no entran); el llamador las pasa como
    ``state``/``history`` a la cadena, rebased a la ventana de 24 h.
    """

    def __init__(self) -> None:
        self._states: dict[str, Any] = {}
        self._accepted: dict[str, list[tuple[datetime, Any]]] = {}

    def state_for(self, equipment: str) -> Any:
        from shield.physics.contract import RoomState

        return self._states.setdefault(equipment or "camara", RoomState())

    def set_state(self, equipment: str, state: Any) -> None:
        self._states[equipment or "camara"] = state

    def recent_actions(self, equipment: str, now: datetime,
                       *, window_h: float = 24.0) -> list[Any]:
        """Acciones aceptadas en la ventana, con start rebased a su inicio."""
        from dataclasses import replace

        hits = [(ts, a) for ts, a in self._accepted.get(equipment or "camara", [])
                if timedelta(0) <= now - ts <= timedelta(hours=window_h)]
        if not hits:
            return []
        t0 = min(ts for ts, _ in hits)
        return [replace(a, start_in_min=(ts - t0).total_seconds() / 60.0)
                for ts, a in sorted(hits, key=lambda x: x[0])]

    def record(self, event: SecurityEvent, decision: str) -> None:
        """Registra la acción solo si la cadena la aceptó (no block)."""
        if decision == "block" or event.app != "cold_room":
            return
        self._accepted.setdefault(event.target or "camara", []).append(
            (event.ts, proposed_action_from_event(event)))


def cold_room_physics_verdict(event: SecurityEvent, *, state: Any | None = None,
                              history: list | None = None,
                              rescue_grant: Any | None = None) -> Any | None:
    """Pasa un evento de frío por la cadena física (M6/M1). None si no aplica.

    Con ``rescue_grant`` firmado de M1 se lo pasa a
    ``verify_before_actuate`` de M6; si el pipeline desplegado aún no lo
    acepta, va directo a ``gate.verify_action(..., rescue_grant=...)``,
    que ya lo verifica. Sin grant, el pipeline manda como siempre.
    """
    if event.app != "cold_room":
        return None
    kind_map = {"set_setpoint": "set_setpoint", "defrost": "defrost",
                "compressor_off": "compressor_off", "door_open": "door_open"}
    if kind_map.get(event.action) is None:
        return None
    from shield.physics.contract import ColdRoomParams, RoomState

    action = proposed_action_from_event(event)
    params = ColdRoomParams()
    room = state or RoomState()
    if rescue_grant is not None:
        from shield.physics.gate import verify_action as gate_verify

        try:  # M6 cuando acepte el grant en su firma.
            from shield.physics.pipeline import verify_before_actuate

            return verify_before_actuate(params, [room], [room.air_c], action,
                                         history=history, rescue_grant=rescue_grant)
        except TypeError:  # pipeline aún sin grant: el gate sí lo verifica
            return gate_verify(params, room, action, history=history,
                               rescue_grant=rescue_grant)
    try:  # M6: verificar-antes-de-actuar (residuo de sensor + gate).
        from shield.physics.pipeline import verify_before_actuate

        return verify_before_actuate(params, [room], [room.air_c], action,
                                     history=history)
    except ImportError:  # pragma: no cover - solo si M6 no está fusionado
        from shield.physics.gate import verify_action

        return verify_action(params, room, action, history=history)
