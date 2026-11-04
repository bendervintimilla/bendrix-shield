"""Grant firmado del rescate: el privilegio no viene de un string.

Un ``requested_by="wairrior-autopilot"`` es texto libre y falsificable
(casos C3-07/C3-08 de M7). El privilegio real es un ``RescueGrant``
con HMAC-SHA256 sobre (equipo, tipo, valor, emisión, expiración y
nonce), con secreto de proceso: se genera al arrancar o se inyecta
con :func:`set_rescue_secret`. Solo lo emite
:func:`issue_last_safe_action`, la función que usa el autopiloto: el
grant vence a los 60 s y su nonce es de un solo uso.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from shield.physics.contract import ColdRoomParams, ProposedAction, RoomState
from shield.physics.safe_state import last_safe_action

GRANT_TTL_S = 60.0

_PROCESS_SECRET: bytes = secrets.token_bytes(32)
_USED_NONCES: set[str] = set()


def set_rescue_secret(secret: bytes | str) -> None:
    """Inyecta el secreto del proceso (arranque del autopiloto/gate)."""
    global _PROCESS_SECRET
    _PROCESS_SECRET = secret.encode() if isinstance(secret, str) else bytes(secret)


def _sign(grant_fields: tuple[str, str, str, str, str, str], secret: bytes) -> str:
    """Firma HMAC-SHA256 hex del payload canónico del grant."""
    payload = "|".join(grant_fields).encode()
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class RescueGrant:
    """Prueba firmada de que el autopiloto emitió un rescate concreto."""

    equipment: str
    kind: str
    value: float | None
    issued_at_s: float
    expires_at_s: float
    nonce: str
    signature: str

    def fields(self) -> tuple[str, str, str, str, str, str]:
        """Campos firmados, en forma canónica."""
        return (
            self.equipment,
            self.kind,
            repr(self.value),
            repr(self.issued_at_s),
            repr(self.expires_at_s),
            self.nonce,
        )


def issue_last_safe_action(
    params: ColdRoomParams,
    state: RoomState,
    *,
    now_s: float | None = None,
    secret: bytes | str | None = None,
) -> tuple[ProposedAction, RescueGrant]:
    """Único emisor del rescate: devuelve la acción y su grant firmado."""
    action = last_safe_action(params, state)
    issued = time.time() if now_s is None else float(now_s)
    key = (
        _PROCESS_SECRET
        if secret is None
        else (secret.encode() if isinstance(secret, str) else bytes(secret))
    )
    unsigned = RescueGrant(
        equipment=action.equipment,
        kind=action.kind,
        value=action.value,
        issued_at_s=issued,
        expires_at_s=issued + GRANT_TTL_S,
        nonce=secrets.token_hex(16),
        signature="",
    )
    return action, RescueGrant(**{**unsigned.__dict__, "signature": _sign(unsigned.fields(), key)})


def check_grant(
    grant: RescueGrant | None,
    params: ColdRoomParams,
    action: ProposedAction,
    *,
    now_s: float | None = None,
    consume: bool = True,
) -> str:
    """Estado del grant: valid | missing | mismatch | bad_signature | expired | reused."""
    if grant is None:
        return "missing"
    if (
        grant.equipment != params.name
        or grant.equipment != action.equipment
        or grant.kind != action.kind
        or grant.value != action.value
    ):
        return "mismatch"
    expected = _sign(grant.fields(), _PROCESS_SECRET)
    if not hmac.compare_digest(expected, grant.signature):
        return "bad_signature"
    now = time.time() if now_s is None else float(now_s)
    if now > grant.expires_at_s or now < grant.issued_at_s:
        return "expired"
    if grant.nonce in _USED_NONCES:
        return "reused"
    if consume:
        _USED_NONCES.add(grant.nonce)
    return "valid"
