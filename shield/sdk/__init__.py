"""SDK bendrix_shield para conectar cualquier app (H3/H4)."""

from shield.policy.injection import UntrustedDoc, untrusted
from shield.sdk.pending import (
    PendingAction,
    PendingRegistry,
    PolicyBlocked,
    PolicyPending,
    default_registry,
)
from shield.sdk.tool import tool

__all__ = [
    "PendingAction",
    "PendingRegistry",
    "PolicyBlocked",
    "PolicyPending",
    "UntrustedDoc",
    "default_registry",
    "tool",
    "untrusted",
]
