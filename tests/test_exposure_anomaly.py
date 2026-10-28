from datetime import UTC, datetime

from shield.anomaly import flag_anomalies
from shield.exposure import match
from shield.schemas import Asset, CallLog, Product, ThreatCard


def test_exposure_name_match():
    threat = ThreatCard(
        id="t1",
        source_url="https://example.com/a",
        products=[Product(name="LiteLLM")],
    )
    assets = [Asset(id="a1", kind="pkg", name="litellm"), Asset(id="a2", kind="pkg", name="flask")]
    found = match(threat, assets)
    assert [e.asset_id for e in found] == ["a1"]


def test_anomaly_spike():
    base = CallLog(ts=datetime.now(UTC), agent="bodega", model="sam-3.1", cost_usd=1.0)
    spike = CallLog(ts=datetime.now(UTC), agent="bodega", model="sam-3.1", cost_usd=100.0)
    assert flag_anomalies([base, base, spike]) == [spike]
    assert flag_anomalies([]) == []
