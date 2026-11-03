"""Registro local del agente: último token Shield válido por agente.

Lo escribe ``shield.actions`` al rotar y lo lee el SDK para recuperarse
solo: Bodega sigue contando sin redeploy ni edición manual.
Solo vive en disco local del agente, nunca en git.

Desde C2490 cada agente tiene su propio archivo: con la ruta base
``~/.shield/agent-tokens.json`` los tokens quedan en
``~/.shield/agent-tokens.d/<agent>.json`` (directorio 0700, archivo 0600).
Un store ligado a un agente (``LocalTokenStore(agent="bodega")``) solo
abre el archivo de ese agente y rechaza leer o escribir el de otro. El
formato viejo (un solo JSON con todos los agentes) se sigue leyendo: al
tocar un agente, su entrada se migra a su archivo y se quita del JSON viejo.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import UTC, datetime
from pathlib import Path

_AGENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$")


def default_store_path() -> Path:
    env = os.environ.get("SHIELD_LOCAL_TOKEN_REGISTRY")
    if env:
        return Path(env)
    return Path.home() / ".shield" / "agent-tokens.json"


def _write_private(path: Path, data: dict) -> None:
    """Escritura atómica con 0600 desde el primer byte (sin ventana abierta)."""
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2))
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    tmp.replace(path)


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


class LocalTokenStore:
    """Un archivo JSON por agente ``{token, token_id, updated_at}``, 0600.

    ``path`` es la ruta base: si termina en ``.json`` es el archivo del
    formato viejo y los archivos por agente van en ``<stem>.d/`` a su lado;
    si no, se usa como directorio. ``agent`` liga el store a un solo agente.
    """

    def __init__(self, path: Path | str | None = None, *, agent: str | None = None) -> None:
        base = Path(path) if path else default_store_path()
        if base.suffix == ".json":
            self.legacy_path: Path | None = base
            self.dir = base.parent / f"{base.stem}.d"
        else:
            self.legacy_path = None
            self.dir = base
        self.path = base
        self.agent = self._valid(agent) if agent is not None else None
        self._lock = threading.Lock()

    @staticmethod
    def _valid(agent: str) -> str:
        if not isinstance(agent, str) or not _AGENT_ID.match(agent):
            raise ValueError(f"agent_id inválido para el token store: {agent!r}")
        return agent

    def _guard(self, agent: str) -> str:
        agent = self._valid(agent)
        if self.agent is not None and agent != self.agent:
            raise PermissionError(
                f"el token store de {self.agent!r} no puede abrir el de {agent!r}"
            )
        return agent

    def path_for(self, agent: str) -> Path:
        """Archivo del agente (no lo crea)."""
        return self.dir / f"{self._guard(agent)}.json"

    def _ensure_dir(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            self.dir.chmod(0o700)
        except OSError:
            pass

    def _drop_legacy(self, agent: str) -> None:
        if self.legacy_path is None or not self.legacy_path.is_file():
            return
        data = _read_json(self.legacy_path)
        if agent not in data:
            return
        data.pop(agent, None)
        if data:
            _write_private(self.legacy_path, data)
        else:
            self.legacy_path.unlink(missing_ok=True)

    def _entry(self, agent: str) -> dict | None:
        agent = self._guard(agent)
        own = self.dir / f"{agent}.json"
        if own.is_file():
            entry = _read_json(own)
            return entry or None
        # Formato viejo: se toma solo la entrada de este agente y se migra.
        if self.legacy_path is None or not self.legacy_path.is_file():
            return None
        entry = _read_json(self.legacy_path).get(agent)
        if not isinstance(entry, dict) or not entry.get("token"):
            return None
        self._ensure_dir()
        _write_private(own, entry)
        self._drop_legacy(agent)
        return entry

    def get_token(self, agent: str) -> str | None:
        with self._lock:
            entry = self._entry(agent)
        return entry.get("token") if entry else None

    def get_token_id(self, agent: str) -> str | None:
        with self._lock:
            entry = self._entry(agent)
        return entry.get("token_id") if entry else None

    def set_token(self, agent: str, raw_token: str, token_id: str | None = None) -> None:
        if not raw_token.startswith("shd_"):
            raise ValueError("Shield token must start with 'shd_'")
        with self._lock:
            agent = self._guard(agent)
            self._ensure_dir()
            _write_private(
                self.dir / f"{agent}.json",
                {
                    "token": raw_token,
                    "token_id": token_id,
                    "updated_at": datetime.now(UTC).isoformat(),
                },
            )
            self._drop_legacy(agent)


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
