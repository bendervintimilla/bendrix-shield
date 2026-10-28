"""SDK bendrix_shield para conectar cualquier app (H3: ``wrap``; H4: tools)."""

from shield.policy.injection import UntrustedDoc, untrusted
from shield.sdk.pending import (
    PendingAction,
    PendingRegistry,
    PolicyBlocked,
    PolicyPending,
    default_registry,
)
from shield.sdk.tool import tool
from shield.sdk.wrap import DEFAULT_GATEWAY_URL, gateway_url, wrap

__all__ = [
    "DEFAULT_GATEWAY_URL",
    "PendingAction",
    "PendingRegistry",
    "PolicyBlocked",
    "PolicyPending",
    "UntrustedDoc",
    "default_registry",
    "gateway_url",
    "tool",
    "untrusted",
    "wrap",
]
