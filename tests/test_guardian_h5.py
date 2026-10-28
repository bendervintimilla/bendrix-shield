import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from shield.agent import GuardianAgent, RegistryActions, SimulatedApprover
from shield.anomaly import detect_anomalies, flagged_logs, load_usage_file
from shield.exposure import match, triage_difficult, version_verdict
from shield.meta_client import NeedsCredits
from shield.notice import draft_both, draft_notice
from shield.registry import Registry
from shield.schemas import Asset, CallLog, Product, ThreatCard

ROOT = Path(__file__).parent.parent


def test_version_verdict_branches():
    affected = ["<8.2.35", "<8.3.36", "<8.4.27", "<8.5.12"]
    fixed = ["8.2.35", "8.3.36", "8.4.27", "8.5.12"]
    assert version_verdict("8.1.20", affected, fixed) == "affected"
    assert version_verdict("8.4.27", affected, fixed) == "safe"
    assert version_verdict("1.82.7", ["1.82.7", "1.82.8"], ["1.82.9"]) == "affected"
    assert version_verdict("1.106.2", ["1.107.0"], ["1.106.2"]) == "safe"
    assert (
        version_verdict("18.0.0", ["self-managed >=7.0 <fixed-2026-10-21"], ["18.11.13"])
        == "unknown"
    )
    assert version_verdict("1.0.9", ["brotli decoder affected builds"], []) == "unknown"


def test_match_confirmed_and_candidate():
    threat = ThreatCard(
        id="CVE-1",
        source_url="https://e.com",
        products=[
            Product(
                name="PHP",
                ecosystem="php",
                affected_versions=["<8.2.35"],
                fixed_versions=["8.2.35"],
            )
        ],
    )
    old = Asset(id="a1", kind="pkg", name="php", metadata={"version": "8.1.20"})
    new = Asset(id="a2", kind="pkg", name="php", metadata={"version": "8.4.27"})
    found = match(threat, [old, new])
    assert [(e.asset_id, e.confidence) for e in found] == [("a1", 0.95)]


class _WonderClient:
    def chat_completions(self, **kwargs):
        assert kwargs["model"] == "muse-wonder-1.0"
        content = json.dumps(
            {
                "decisions": [
                    {
                        "threat_id": "CVE-9",
                        "asset_id": "a1",
                        "exposed": True,
                        "reason": "afectado",
                        "confidence": 0.9,
                    }
                ]
            }
        )
        return SimpleNamespace(
            data={"choices": [{"message": {"content": content}}]}, cost_usd=0.002
        )

    def close(self):
        pass


class _NoCreditsClient:
    def chat_completions(self, **kwargs):
        raise NeedsCredits(402, "billing")

    def close(self):
        pass


def test_wonder_triage_only_for_candidates():
    threat = ThreatCard(
        id="CVE-9",
        source_url="https://e.com",
        products=[Product(name="Brotli", affected_versions=["builds afectados"])],
    )
    asset = Asset(id="a1", kind="pkg", name="brotli", metadata={"version": "1.0.9"})
    result = triage_difficult([threat], [asset], client=_WonderClient())
    assert result.triaged == 1 and result.exposures[0].confidence == 0.9
    offline = triage_difficult([threat], [asset], client=_NoCreditsClient())
    assert offline.needs_credits is True and "needs_wonder" in offline.exposures[0].reason


def test_anomaly_on_h2_usage_series():
    normal, _ = load_usage_file(ROOT / "evals/usage/crew-bodega_normal_7d.json")
    abuse, _ = load_usage_file(ROOT / "evals/usage/crew-bodega_abuse_16h.json")
    kinds = {f.kind for f in detect_anomalies(abuse, normal)}
    assert {"new_country", "new_model", "cost_spike"} <= kinds
    assert len(flagged_logs(abuse, normal)) >= 29
    assert flagged_logs(normal[len(normal) // 2 :], normal[: len(normal) // 2]) == []


def _logs(agent: str, country: str, model: str, cost: float, n: int = 3) -> list[CallLog]:
    return [
        CallLog(
            ts=datetime(2026, 10, 20, 8 + i, tzinfo=UTC),
            agent=agent,
            model=model,
            cost_usd=cost,
            src_country=country,
        )
        for i in range(n)
    ]


def test_guardian_rotates_only_anomalous_agent_after_approval():
    registry = Registry(":memory:")
    bodega, _ = registry.create_token("bodega", "crew", models=["sam-3.1"])
    compras, _ = registry.create_token("compras", "crew", models=["muse-spark-1.3"])
    baseline = _logs("bodega", "EC", "sam-3.1", 1.0)
    abuse = _logs("bodega", "BR", "muse-spark-1.3", 18.0)
    approver = SimulatedApprover(approve=True)
    guardian = GuardianAgent(
        logs=abuse, baseline=baseline, actions=RegistryActions(registry), approver=approver
    )
    report = guardian.run_once()
    assert report.approval_id and approver.asked
    assert any(
        e["action"] == "rotate_token" and e["target"] == "bodega" and e["status"] == "rotated"
        for e in report.executed
    )
    assert registry.get_token(compras.token_id).status.value == "active"
    assert registry.get_token(bodega.token_id).status.value == "rotated"
    assert any(
        t.agent == "bodega" and t.status.value == "active" for t in registry.list_tokens("bodega")
    )
    registry.close()


def test_guardian_without_approval_executes_nothing():
    registry = Registry(":memory:")
    token, _ = registry.create_token("bodega", "crew")
    guardian = GuardianAgent(
        logs=_logs("bodega", "BR", "muse-spark-1.3", 18.0),
        baseline=_logs("bodega", "EC", "sam-3.1", 1.0),
        actions=RegistryActions(registry),
        approver=SimulatedApprover(approve=False),
    )
    blocked = guardian.dispatch("rotate_token", {"agent": "bodega", "approval_id": "inventado"})
    assert blocked["status"] == "blocked"
    report = guardian.run_once()
    assert report.executed == [] and report.approval_id is None
    assert registry.get_token(token.token_id).status.value == "active"
    registry.close()


class _ToolLoopClient:
    def __init__(self):
        self.calls = 0

    def chat_completions(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            data = {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "type": "function",
                                    "function": {"name": "detect_anomaly", "arguments": "{}"},
                                }
                            ],
                        }
                    }
                ]
            }
        else:
            data = {"choices": [{"message": {"content": "ciclo completo"}}]}
        return SimpleNamespace(data=data, cost_usd=0.0)

    def close(self):
        pass


def test_guardian_model_tool_loop_and_notice_marks():
    guardian = GuardianAgent(
        logs=_logs("bodega", "BR", "muse-spark-1.3", 18.0),
        baseline=_logs("bodega", "EC", "sam-3.1", 1.0),
        client=_ToolLoopClient(),
    )
    report = guardian.run_with_model()
    assert report.anomalies and report.summary.startswith("model-loop")
    drafts = draft_both(summary="prueba", exposures=[], anomalies=report.anomalies)
    assert {d.regime for d in drafts} == {"rgpd", "lopdp"}
    assert all("BORRADOR" in d.render() and "lo revisa un humano" in d.render() for d in drafts)
    single = draft_notice(summary="x", regime="lopdp")
    assert "Superintendencia de Protección de Datos Personales" in single.body
