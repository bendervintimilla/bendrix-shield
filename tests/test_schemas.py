from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from shield.schemas import (
    AgentToken,
    AgentTokenStatus,
    Asset,
    CallLog,
    Decision,
    Exposure,
    PolicyDecision,
    Product,
    ThreatCard,
    ToolCall,
)


def test_threat_card_roundtrip():
    card = ThreatCard(
        id="CVE-TEST-1",
        source_url="https://example.com/advisory",
        published_at=datetime(2026, 10, 21, tzinfo=UTC),
        products=[Product(name="litellm", ecosystem="pypi", affected_versions=["1.107.0"])],
        severity="high",
    )
    assert card.products[0].fixed_versions == []
    assert ThreatCard.model_validate_json(card.model_dump_json()).id == "CVE-TEST-1"


def test_exposure_confidence_bounds():
    ok = Exposure(threat_id="t", asset_id="a", reason="match", confidence=0.9)
    assert ok.confidence == 0.9
    with pytest.raises(ValidationError):
        Exposure(threat_id="t", asset_id="a", reason="x", confidence=1.5)


def test_agent_token_defaults():
    tok = AgentToken(token_id="shd_bodega_x", agent="bodega", app="crew")
    assert tok.status is AgentTokenStatus.ACTIVE
    assert tok.scopes == []


def test_call_log_and_policy_decision():
    log = CallLog(ts=datetime.now(UTC), agent="bodega", model="sam-3.1", decision=Decision.BLOCK)
    assert log.tokens_in == 0
    decision = PolicyDecision(decision=Decision.ASK_OWNER, reason="iban change")
    assert decision.evidence == []
    call = ToolCall(agent="compras", tool="pay", args_redacted={"iban": "***"})
    assert call.source_doc_ids == []
    asset = Asset(id="a1", kind="api_key", name="gemini")
    assert asset.metadata == {}
