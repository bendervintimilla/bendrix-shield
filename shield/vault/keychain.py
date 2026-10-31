"""Backend llavero de macOS (``security`` CLI). El valor nunca se imprime."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Any

from shield.vault.vault import BaseVault, VaultUnavailable

Runner = Callable[..., Any]


class KeychainVault(BaseVault):
    """Guarda cada secreto como generic-password con cuenta fija ``hackathon``."""

    def __init__(self, account: str = "hackathon", runner: Runner | None = None) -> None:
        self._account = account
        self._run = runner or subprocess.run

    def _call(self, args: list[str]) -> Any:
        try:
            return self._run(args, capture_output=True, text=True, timeout=10)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise VaultUnavailable("macOS `security` CLI not available") from exc

    def get(self, name: str) -> str | None:
        # El llavero guarda «meta-model-api-key»; el código pide «META_MODEL_API_KEY».
        alias = name.lower().replace("_", "-")
        for service in dict.fromkeys((name, alias)):
            out = self._call(
                ["security", "find-generic-password", "-s", service, "-a", self._account, "-w"]
            )
            value = out.stdout.strip() if out.returncode == 0 else ""
            if value:
                return value
        return None

    def put(self, name: str, value: str) -> None:
        if not value:
            raise ValueError("vault value must not be empty")
        out = self._call(
            [
                "security",
                "add-generic-password",
                "-U",
                "-s",
                name,
                "-a",
                self._account,
                "-w",
                value,
            ]
        )
        if out.returncode != 0:
            raise VaultUnavailable(f"keychain put failed for {name}")
