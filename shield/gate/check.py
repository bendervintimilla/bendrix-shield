"""`gate.check(payload)` — hook obligatorio antes de todo envío saliente.

bloqueo de canarios, redacción determinista de llaves/PII
(ver ``gate/redact.py``; el payload redactado va en
``GateResult.redacted`` y el gateway reenvía ese), alerta al detectar
un canario (hook registrable, por defecto log) y clasificación vía
``gate.classify``.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from shield.gate.canaries import find_canaries
from shield.gate.classify import Classification, classify
from shield.gate.open_classifier import BLOCK_LABELS, BLOCK_THRESHOLD
from shield.gate.redact import Redaction, redact_payload

logger = logging.getLogger("shield.gate")

AlertHook = Callable[[list[str]], None]
_alert_hook: AlertHook | None = None


def set_alert_hook(hook: AlertHook | None) -> None:
    global _alert_hook
    _alert_hook = hook


def _alert(canaries: list[str]) -> None:
    # Solo nombres de canarios sintéticos; ningún secreto real llega aquí.
    logger.warning("gate canary blocked canaries=%s", canaries)
    if _alert_hook is not None:
        _alert_hook(canaries)


class GateBlocked(RuntimeError):
    """El payload contiene un canario y no debe salir."""


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    canaries_found: list[str] = field(default_factory=list)
    reason: str = ""
    redactions: list[Redaction] = field(default_factory=list)
    redacted: object = None
    classification: Classification | None = None


def _to_text(payload: object) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="ignore")
    try:
        return json.dumps(payload, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(payload)


def check(payload: object, *, canaries: list[str] | tuple[str, ...] | None = None) -> GateResult:
    text = _to_text(payload)
    found = find_canaries(text, canaries=tuple(canaries) if canaries else None)
    if found:
        _alert(found)
        return GateResult(allowed=False, canaries_found=found, reason="canary_in_payload")
    redacted, redactions = redact_payload(payload)
    classification = classify(text)
    # Spark Open sí bloquea con confianza alta; el stub y needs_credits no.
    if (
        classification is not None
        and classification.label in BLOCK_LABELS
        and classification.score >= BLOCK_THRESHOLD
    ):
        return GateResult(
            allowed=False,
            reason=f"spark_open_{classification.label}",
            redactions=redactions,
            redacted=redacted,
            classification=classification,
        )
    return GateResult(
        allowed=True,
        reason="ok",
        redactions=redactions,
        redacted=redacted,
        classification=classification,
    )


def check_or_raise(payload: object, *, canaries: list[str] | tuple[str, ...] | None = None) -> None:
    result = check(payload, canaries=canaries)
    if not result.allowed:
        raise GateBlocked(f"gate blocked payload: canaries={result.canaries_found}")
