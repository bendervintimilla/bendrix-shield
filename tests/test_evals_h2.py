import json
from pathlib import Path

R = Path(__file__).parent.parent
def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def test_advisories_reales():
    fs = sorted((R/"evals/advisories").glob("*.json")); assert len(fs) >= 12
    from shield.schemas import ThreatCard
    for f in fs:
        d = load(f); ThreatCard(id=d["id"], source_url=d["source_url"], products=d.get("products", []))
        assert d["source_url"].startswith("https://")
def test_estates_30_con_negativos():
    fs = sorted((R/"evals/estates").glob("*.json")); assert len(fs) >= 30
    assert any(any(not e["exposed"] for e in load(f)["expected_exposures"]) for f in fs)
def test_injection_30_mas_30():
    inj = R/"evals/injection"
    assert len(list(inj.glob("poison-*.json"))) >= 30 and len(list(inj.glob("clean-*.json"))) >= 30
    assert all(load(f)["expected_policy"] == "block" for f in inj.glob("poison-*.json"))
def test_invoices_y_canarios():
    assert len(list((R/"evals/invoices").glob("*.json"))) == 20
    assert all(load(f)["ground_truth"]["total"] for f in (R/"evals/invoices").glob("*.json"))
    cans = load(R/"evals/canaries.json")["canaries"]; assert len(cans) == 10
    from shield.gate import check
    assert all(check(f"x {c} y", canaries=cans).allowed is False for c in cans)
def test_uso_abuso_16h():
    d = load(R/"evals/usage/crew-bodega_abuse_16h.json")
    assert d["duration_hours"] == 16 and len(d["calls"]) > 30
    assert {c["src_country"] for c in d["calls"]} == {"EC", "BR"}
def test_attacker_solo_sandbox():
    import importlib.util
    spec = importlib.util.spec_from_file_location("attacker", R/"sandbox/attacker.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    assert m.assert_allowed("http://127.0.0.1:8000/v1/chat/completions")
    try:
        m.assert_allowed("https://example.com/v1/chat/completions"); assert False
    except SystemExit: pass
