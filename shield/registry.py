"""Registro SQLite de tokens de agente y llamadas (gateway).

Solo se guarda el **hash sha256** del token Shield, nunca el token en claro.
Formato del token: ``shd_<agente>_<aleatorio>``. Un agente = un token = un
alcance: rotar o revocar uno no toca a ningún otro (invariante ).
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from shield.schemas import AgentToken, AgentTokenStatus, CallLog, Decision


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_raw_token(agent: str) -> str:
    safe_agent = (
        "".join(c if c.isalnum() or c in "-_" else "-" for c in agent).strip("-") or "agent"
    )
    return f"shd_{safe_agent}_{secrets.token_urlsafe(24)}"


class Registry:
    """SQLite (archivo o ``:memory:``) con AgentToken y CallLog del """

    def __init__(self, db_path: str | Path | None = None) -> None:
        path = db_path or os.environ.get("SHIELD_REGISTRY_DB") or "shield-registry.db"
        self._path = str(path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_tokens (
                    token_id TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL UNIQUE,
                    agent TEXT NOT NULL,
                    app TEXT NOT NULL,
                    scopes TEXT NOT NULL DEFAULT '[]',
                    models TEXT NOT NULL DEFAULT '[]',
                    spend_cap_usd REAL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS call_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    model TEXT NOT NULL,
                    tokens_in INTEGER NOT NULL DEFAULT 0,
                    tokens_out INTEGER NOT NULL DEFAULT 0,
                    cost_usd REAL NOT NULL DEFAULT 0,
                    latency_ms REAL NOT NULL DEFAULT 0,
                    src_ip TEXT,
                    src_country TEXT,
                    decision TEXT NOT NULL DEFAULT 'allow'
                );
                """
            )

    def close(self) -> None:
        self._conn.close()

    # -- tokens -----------------------------------------------------------
    def create_token(
        self,
        agent: str,
        app: str,
        *,
        scopes: list[str] | None = None,
        models: list[str] | None = None,
        spend_cap_usd: float | None = None,
    ) -> tuple[AgentToken, str]:
        raw = new_raw_token(agent)
        token = AgentToken(
            token_id=f"shd_{agent}_{secrets.token_hex(4)}",
            agent=agent,
            app=app,
            scopes=list(scopes or []),
            models=list(models or []),
            spend_cap_usd=spend_cap_usd,
            status=AgentTokenStatus.ACTIVE,
        )
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO agent_tokens VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    token.token_id,
                    hash_token(raw),
                    token.agent,
                    token.app,
                    json.dumps(token.scopes),
                    json.dumps(token.models),
                    token.spend_cap_usd,
                    token.status.value,
                    datetime.now(UTC).isoformat(),
                ),
            )
        return token, raw

    @staticmethod
    def _row_to_token(row: sqlite3.Row) -> AgentToken:
        return AgentToken(
            token_id=row["token_id"],
            agent=row["agent"],
            app=row["app"],
            scopes=json.loads(row["scopes"]),
            models=json.loads(row["models"]),
            spend_cap_usd=row["spend_cap_usd"],
            status=AgentTokenStatus(row["status"]),
        )

    def authenticate(self, raw: str | None) -> AgentToken | None:
        """Devuelve el AgentToken del token en claro, o None si no existe."""
        if not raw:
            return None
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM agent_tokens WHERE token_hash=?", (hash_token(raw),)
            ).fetchone()
        return self._row_to_token(row) if row else None

    def get_token(self, token_id: str) -> AgentToken | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM agent_tokens WHERE token_id=?", (token_id,)
            ).fetchone()
        return self._row_to_token(row) if row else None

    def list_tokens(self, agent: str | None = None) -> list[AgentToken]:
        with self._lock:
            if agent:
                rows = self._conn.execute(
                    "SELECT * FROM agent_tokens WHERE agent=? ORDER BY created_at", (agent,)
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM agent_tokens ORDER BY created_at"
                ).fetchall()
        return [self._row_to_token(r) for r in rows]

    def _set_status(self, token_id: str, status: AgentTokenStatus) -> AgentToken | None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE agent_tokens SET status=? WHERE token_id=?", (status.value, token_id)
            )
        return self.get_token(token_id)

    def revoke(self, token_id: str) -> AgentToken | None:
        return self._set_status(token_id, AgentTokenStatus.REVOKED)

    def rotate(self, token_id: str) -> tuple[AgentToken, str] | None:
        """Rota solo ese token: el viejo queda ``rotated`` y nace uno nuevo.

        Los demás agentes (y otros tokens del mismo agente) no se tocan.
        """
        old = self.get_token(token_id)
        if old is None:
            return None
        self._set_status(token_id, AgentTokenStatus.ROTATED)
        return self.create_token(
            old.agent,
            old.app,
            scopes=list(old.scopes),
            models=list(old.models),
            spend_cap_usd=old.spend_cap_usd,
        )

    # -- llamadas ---------------------------------------------------------
    def record_call(self, log: CallLog) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO call_logs"
                " (ts, agent, model, tokens_in, tokens_out, cost_usd, latency_ms,"
                " src_ip, src_country, decision) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    log.ts.isoformat(),
                    log.agent,
                    log.model,
                    log.tokens_in,
                    log.tokens_out,
                    log.cost_usd,
                    log.latency_ms,
                    log.src_ip,
                    log.src_country,
                    log.decision.value,
                ),
            )

    def list_calls(self, agent: str | None = None) -> list[CallLog]:
        with self._lock:
            if agent:
                rows = self._conn.execute(
                    "SELECT * FROM call_logs WHERE agent=? ORDER BY id", (agent,)
                ).fetchall()
            else:
                rows = self._conn.execute("SELECT * FROM call_logs ORDER BY id").fetchall()
        return [
            CallLog(
                ts=datetime.fromisoformat(r["ts"]),
                agent=r["agent"],
                model=r["model"],
                tokens_in=r["tokens_in"],
                tokens_out=r["tokens_out"],
                cost_usd=r["cost_usd"],
                latency_ms=r["latency_ms"],
                src_ip=r["src_ip"],
                src_country=r["src_country"],
                decision=Decision(r["decision"]),
            )
            for r in rows
        ]

    def total_spend_usd(self, agent: str) -> float:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(cost_usd),0) AS total FROM call_logs"
                " WHERE agent=? AND decision='allow'",
                (agent,),
            ).fetchone()
        return float(row["total"])

    def latency_percentile(self, p: float = 50.0, agent: str | None = None) -> float | None:
        """Percentil de latencia registrada (ms); alimenta docs/GATEWAY.md."""
        values = sorted(c.latency_ms for c in self.list_calls(agent) if c.latency_ms > 0)
        if not values:
            return None
        idx = min(max(int(round((p / 100.0) * (len(values) - 1))), 0), len(values) - 1)
        return values[idx]
