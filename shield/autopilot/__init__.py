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
    ColdRoomHistory,
    SecurityEvent,
    build_internal_rescue_action,
    cold_room_physics_verdict,
    emit_safe_state_rescue,
    from_cold_room,
    from_gateway_call,
    from_payment,
    from_pos_erp,
    from_webhook,
    proposed_action_from_event,
    verify_rescue,
)
from shield.autopilot.respond import (
    ContainmentEngine,
    ContainmentResult,
    InMemoryTokenOps,
    Measure,
    ShieldActionsTokenOps,
    build_business_notice,
    build_owner_notice,
    dispatch_notice_sandbox,
    operation_scope,
    respond,
    run_pipeline,
)

__all__ = [
    "APPS", "ActorBaseline", "ColdRoomHistory", "ContainmentEngine", "ContainmentResult",
    "Finding", "InMemoryTokenOps", "Incident", "Measure", "SecurityEvent",
    "ShieldActionsTokenOps", "build_business_notice", "operation_scope",
    "build_internal_rescue_action", "build_owner_notice",
    "cold_room_physics_verdict", "emit_safe_state_rescue",
    "proposed_action_from_event", "verify_rescue", "correlate", "detect",
    "dispatch_notice_sandbox", "from_cold_room", "from_gateway_call",
    "from_payment", "from_pos_erp", "from_webhook", "respond",
    "run_pipeline", "triage_incident",
]
