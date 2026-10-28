"""Vault de llaves reales: interfaz común y backend en memoria (tests).

El valor de un secreto nunca se loguea ni aparece en ``repr``: fuera del
``get`` solo salen nombre, huella (sha256[:8]) y últimos 4 caracteres.
"""

from __future__ import annotations

import hashlib
import os
from typing import Protocol, runtime_checkable


class VaultUnavailable(RuntimeError):
    """El backend pedido no está disponible en este entorno."""


def fingerprint_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


@runtime_checkable
class Vault(Protocol):
    def get(self, name: str) -> str | None: ...
    def put(self, name: str, value: str) -> None: ...
    def fingerprint(self, name: str) -> str | None: ...
    def last4(self, name: str) -> str | None: ...


class BaseVault:
    """Implementa huella/last4 sobre ``get`` para no repetirlo por backend."""

    def get(self, name: str) -> str | None:  # pragma: no cover - interfaz
        raise NotImplementedError

    def put(self, name: str, value: str) -> None:  # pragma: no cover - interfaz
        raise NotImplementedError

    def fingerprint(self, name: str) -> str | None:
        value = self.get(name)
        return fingerprint_value(value) if value is not None else None

    def last4(self, name: str) -> str | None:
        value = self.get(name)
        if value is None:
            return None
        return value[-4:] if len(value) >= 4 else "****"

    def describe(self, name: str) -> dict[str, str | None]:
        """Lo único que se puede loguear de un secreto."""
        return {"name": name, "fingerprint": self.fingerprint(name), "last4": self.last4(name)}

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"


class MemoryVault(BaseVault):
    """Backend en memoria: tests y modo replay. Nunca para producción."""

    def __init__(self, initial: dict[str, str] | None = None) -> None:
        self._store: dict[str, str] = dict(initial or {})

    def get(self, name: str) -> str | None:
        return self._store.get(name)

    def put(self, name: str, value: str) -> None:
        if not value:
            raise ValueError("vault value must not be empty")
        self._store[name] = value

    def delete(self, name: str) -> None:
        self._store.pop(name, None)

    def names(self) -> list[str]:
        return sorted(self._store)

    def __repr__(self) -> str:
        return f"MemoryVault(names={self.names()!r})"


def get_vault(backend: str | None = None, **kwargs: object) -> BaseVault:
    """Fábrica por entorno: SHIELD_VAULT_BACKEND=memory|keychain|secret-manager."""
    chosen = (backend or os.environ.get("SHIELD_VAULT_BACKEND") or "keychain").lower()
    if chosen == "memory":
        return MemoryVault()
    if chosen == "keychain":
        from shield.vault.keychain import KeychainVault

        return KeychainVault(**kwargs)  # type: ignore[arg-type]
    if chosen in ("secret-manager", "secretmanager", "gcp"):
        from shield.vault.secret_manager import SecretManagerVault

        return SecretManagerVault(**kwargs)  # type: ignore[arg-type]
    raise VaultUnavailable(f"unknown vault backend: {chosen}")
