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


def test_phone_no_toca_cve_ni_ids_con_prefijo_letra_guion():
    # Antes: 'CVE-2026-1234' salía como 'CVE-[REDACTED:phone]' en la UI del guardián.
    for ident in (
        "CVE-2026-1234",
        "CVE-2026-0322",
        "CVE-2026-105133",
        "ref ABC-1234-5678",
        "chatcmpl-01a19d7f-e123-4567-b54c-b421ac175146",
        "a49e883d-1234-5678-838f-45576e2e8830",
        "01a19d80-1234-5678-8ea5-abd08b2a7252",
    ):
        redacted, kinds = redact_text(f'{{"id": "{ident}"}}')
        assert ident in redacted, ident
        assert "phone" not in {f.kind for f in kinds}, ident


def test_phone_sigue_redactando_telefonos():
    for tel in ("+593 99 123 4567", "099 123 4567", "(02) 234-5678", "+593991112233", "2345-6789"):
        redacted, kinds = redact_text(f"llamar al {tel}.")
        assert tel not in redacted, tel
        assert "phone" in {f.kind for f in kinds}, tel
