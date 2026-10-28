"""Vault de llaves reales de Shield (H3). El valor nunca se loguea."""

from shield.vault.keychain import KeychainVault
from shield.vault.secret_manager import SecretManagerVault
from shield.vault.vault import (
    BaseVault,
    MemoryVault,
    Vault,
    VaultUnavailable,
    fingerprint_value,
    get_vault,
)

__all__ = [
    "BaseVault",
    "KeychainVault",
    "MemoryVault",
    "SecretManagerVault",
    "Vault",
    "VaultUnavailable",
    "fingerprint_value",
    "get_vault",
]
