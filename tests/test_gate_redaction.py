from shield.gate import check, classify, redact_text, set_alert_hook

SECRETS = [
    "sk-" + "liveA1b2C3d4E5f6G7h8",
    "AIza" + "SyD4iE2vA9xK8mN3pQ7rS5tU",
    "LLM_" + "SECRET_abc12345",
    "ghp_" + "1234567890abcdefXYZ",
    "github_pat_" + "11ABCDEFG0a1b2c3d4e5f6g7",
    "AKIA" + "IOSFODNN7EXAMPLE",
    "eyJ" + "hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3AAAA",
]


def test_redacts_each_key_kind_without_leaking_value():
    for secret in SECRETS:
        redacted, findings = redact_text(f"valor: {secret} fin")
        assert secret not in redacted
        assert "[REDACTED:" in redacted
        assert findings, secret[:6]


def test_redacts_pii():
    text = (
        "escribe a maria.perez@example.ec, tel +593 99 123 4567, IBAN ES91 2100 0418 4502 0005 1332"
    )
    redacted, kinds = redact_text(text)
    assert "maria.perez@example.ec" not in redacted
    assert "ES91" not in redacted
    found = {f.kind for f in kinds}
    assert {"email", "iban"} <= found
    assert "phone" in found


def test_check_returns_redacted_payload_and_keeps_original_keys_out():
    result = check({"messages": [{"content": "mi llave es " + "sk-" + "liveA1b2C3d4E5f6G7h8"}]})
    assert result.allowed is True
    assert result.redactions
    assert "liveA1b2" not in str(result.redacted)


def test_canary_blocks_and_alerts():
    seen = []
    set_alert_hook(seen.append)
    try:
        result = check("salida con CANARY-SHIELD-0001 dentro")
    finally:
        set_alert_hook(None)
    assert result.allowed is False
    assert seen == [["CANARY-SHIELD-0001"]]


def test_classify_is_honest_stub():
    result = classify("cualquier texto")
    assert result.label == "unclassified"
    assert result.model == "stub"
