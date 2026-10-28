"""Bendrix Shield — capa de seguridad para agentes y apps de IA."""

from shield.policy.injection import UntrustedDoc, untrusted
from shield.sdk.tool import tool
from shield.sdk.wrap import wrap

__version__ = "0.1.0"

__all__ = ["UntrustedDoc", "tool", "untrusted", "wrap"]
