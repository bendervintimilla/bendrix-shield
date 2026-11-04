"""wAIrrior Autopilot (M10): vigía entre apps con contención automática."""

from shield.autopilot.detect import (
    ActorBaseline,
    Finding,
    Incident,
    correlate,
    detect,
    triage_incident,
)
from shield.autopilot.events import (
    APPS,
    SecurityEvent,
    cold_room_physics_verdict,
    from_cold_room,
    from_gateway_call,
    from_payment,
    from_pos_erp,
    from_webhook,
)
from shield.autopilot.respond import (
    ContainmentEngine,
    ContainmentResult,
    InMemoryTokenOps,
    Measure,
    build_owner_notice,
    dispatch_notice_sandbox,
    respond,
    run_pipeline,
)

__all__ = [
    "APPS", "ActorBaseline", "ContainmentEngine", "ContainmentResult",
    "Finding", "InMemoryTokenOps", "Incident", "Measure", "SecurityEvent",
    "build_owner_notice", "cold_room_physics_verdict", "correlate", "detect",
    "dispatch_notice_sandbox", "from_cold_room", "from_gateway_call",
    "from_payment", "from_pos_erp", "from_webhook", "respond",
    "run_pipeline", "triage_incident",
]
