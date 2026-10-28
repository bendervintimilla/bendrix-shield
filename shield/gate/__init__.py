"""Filtro de salida de Shield (gate)."""

from shield.gate.canaries import DEFAULT_CANARIES, find_canaries
from shield.gate.check import GateBlocked, GateResult, check, check_or_raise, set_alert_hook
from shield.gate.classify import (
    Classification,
    Classifier,
    StubClassifier,
    classify,
    get_classifier,
    set_classifier,
)
from shield.gate.open_classifier import (
    SparkOpenClassifier,
    deterministic_alone,
    make_open_classifier,
)
from shield.gate.redact import Redaction, redact_payload, redact_text

__all__ = [
    "DEFAULT_CANARIES",
    "Classification",
    "Classifier",
    "GateBlocked",
    "GateResult",
    "Redaction",
    "SparkOpenClassifier",
    "StubClassifier",
    "check",
    "check_or_raise",
    "classify",
    "deterministic_alone",
    "find_canaries",
    "get_classifier",
    "make_open_classifier",
    "redact_payload",
    "redact_text",
    "set_alert_hook",
    "set_classifier",
]
