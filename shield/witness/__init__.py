"""wAIrrior Witness: la cámara como testigo físico (SAM 3.1, redactado RGPD)."""

from shield.witness.observe import (
    DEFAULT_CONCEPTS,
    DEFAULT_DOOR_CONCEPTS,
    WitnessObservation,
    observe,
)
from shield.witness.redact import blur_whole, redact
from shield.witness.registry import (
    DEFAULT_MAX_AGE_S,
    WitnessRegistry,
    default_registry,
    is_stale,
    presence,
    record,
)

__all__ = [
    "DEFAULT_CONCEPTS", "DEFAULT_DOOR_CONCEPTS", "DEFAULT_MAX_AGE_S",
    "WitnessObservation", "WitnessRegistry", "blur_whole", "default_registry",
    "is_stale", "observe", "presence", "record", "redact",
]
