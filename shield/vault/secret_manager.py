"""Backend Google Secret Manager (proyecto de ``SHIELD_GCP_PROJECT``).

Usa ``google-cloud-secret-manager`` si está instalado (import perezoso: no es
dependencia dura, el gateway local corre con llavero o memoria). El cliente se
puede inyectar en tests con la misma interfaz mínima.
"""

from __future__ import annotations

import os
from typing import Any

from shield.vault.vault import BaseVault, VaultUnavailable

DEFAULT_PROJECT = ""  # sin default: el proyecto sale de SHIELD_GCP_PROJECT


class SecretManagerVault(BaseVault):
    def __init__(self, project: str | None = None, client: Any | None = None) -> None:
        self._project = (
            project
            or os.environ.get("SHIELD_GCP_PROJECT")
            or os.environ.get("GCP_PROJECT")
            or DEFAULT_PROJECT
        )
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                from google.cloud import secretmanager
            except ImportError as exc:
                raise VaultUnavailable(
                    "google-cloud-secret-manager not installed; "
                    "install it or use SHIELD_VAULT_BACKEND=keychain|memory"
                ) from exc
            self._client = secretmanager.SecretManagerServiceClient()
        return self._client

    def _secret_path(self, name: str) -> str:
        return f"projects/{self._project}/secrets/{name}"

    def get(self, name: str) -> str | None:
        try:
            resp = self.client.access_secret_version(
                request={"name": f"{self._secret_path(name)}/versions/latest"}
            )
        except Exception:
            return None
        return resp.payload.data.decode("utf-8")

    def put(self, name: str, value: str) -> None:
        if not value:
            raise ValueError("vault value must not be empty")
        parent = f"projects/{self._project}"
        try:
            self.client.get_secret(request={"name": self._secret_path(name)})
        except Exception:
            self.client.create_secret(
                request={
                    "parent": parent,
                    "secret_id": name,
                    "secret": {"replication": {"automatic": {}}},
                }
            )
        self.client.add_secret_version(
            request={"parent": self._secret_path(name), "payload": {"data": value.encode()}}
        )
