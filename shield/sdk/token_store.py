"""Registro local del agente: último token Shield válido por agente.

Lo escribe ``shield.actions`` al rotar y lo lee el SDK para recuperarse
solo: Bodega sigue contando sin redeploy ni edición manual.
Solo vive en disco local del agente (0600), nunca en git.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path


def default_store_path() -> Path:
    env = os.environ.get("SHIELD_LOCAL_TOKEN_REGISTRY")
    if env:
        return Path(env)
    return Path.home() / ".shield" / "agent-tokens.json"


class LocalTokenStore:
    """JSON local ``{agent: {token, token_id, updated_at}}`` con escritura atómica."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else default_store_path()
        self._lock = threading.Lock()

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def get_token(self, agent: str) -> str | None:
        with self._lock:
            entry = self._read().get(agent)
        return entry.get("token") if isinstance(entry, dict) else None

    def get_token_id(self, agent: str) -> str | None:
        with self._lock:
            entry = self._read().get(agent)
        return entry.get("token_id") if isinstance(entry, dict) else None

    def set_token(self, agent: str, raw_token: str, token_id: str | None = None) -> None:
        if not raw_token.startswith("shd_"):
            raise ValueError("Shield token must start with 'shd_'")
        with self._lock:
            data = self._read()
            data[agent] = {
                "token": raw_token,
                "token_id": token_id,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            try:
                tmp.chmod(0o600)
            except OSError:
                pass
            tmp.replace(self.path)


class InMemoryTokenStore:
    """Misma interfaz, sin disco: tests y replay."""

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}

    def get_token(self, agent: str) -> str | None:
        entry = self._data.get(agent)
        return entry["token"] if entry else None

    def get_token_id(self, agent: str) -> str | None:
        entry = self._data.get(agent)
        return entry.get("token_id") if entry else None

    def set_token(self, agent: str, raw_token: str, token_id: str | None = None) -> None:
        if not raw_token.startswith("shd_"):
            raise ValueError("Shield token must start with 'shd_'")
        self._data[agent] = {"token": raw_token, "token_id": token_id}
