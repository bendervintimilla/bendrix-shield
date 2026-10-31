"""Esquemas compartidos. Fuente única para gateway, gate, policy y evals."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Product(BaseModel):
    name: str
    ecosystem: str | None = None
    affected_versions: list[str] = Field(default_factory=list)
    fixed_versions: list[str] = Field(default_factory=list)


class ThreatCard(BaseModel):
    id: str
    source_url: str
    published_at: datetime | None = None
    products: list[Product] = Field(default_factory=list)
    iocs: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    severity: str | None = None


class Asset(BaseModel):
    id: str
    kind: str
    name: str
    owner_app: str | None = None
    platform: str | None = None
    fingerprint: str | None = None
    last4: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class Exposure(BaseModel):
    threat_id: str
    asset_id: str
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)


class AgentTokenStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    ROTATED = "rotated"


class AgentToken(BaseModel):
    token_id: str
    agent: str
    app: str
    scopes: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    spend_cap_usd: float | None = None
    status: AgentTokenStatus = AgentTokenStatus.ACTIVE


class Decision(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    ASK_OWNER = "ask_owner"


class CallLog(BaseModel):
    ts: datetime
    agent: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    src_ip: str | None = None
    src_country: str | None = None
    decision: Decision = Decision.ALLOW


class ToolCall(BaseModel):
    agent: str
    tool: str
    args_redacted: dict[str, object] = Field(default_factory=dict)
    source_doc_ids: list[str] = Field(default_factory=list)


class PolicyDecision(BaseModel):
    decision: Decision
    reason: str
    evidence: list[str] = Field(default_factory=list)
