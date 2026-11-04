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


def test_phone_no_toca_cve():
    # Antes: 'CVE-2026-1234' salía como 'CVE-[REDACTED:phone]' en la UI del guardián.
    for ident in ("CVE-2026-1234", "CVE-2026-0322", "CVE-2026-105133", "ver CVE-2025-12345."):
        redacted, kinds = redact_text(f'{{"id": "{ident}"}}')
        assert ident in redacted, ident
        assert "phone" not in {f.kind for f in kinds}, ident


def test_cve_y_telefono_en_el_mismo_texto():
    redacted, kinds = redact_text("CVE-2026-1234 reportado por +593991234567")
    assert redacted == "CVE-2026-1234 reportado por [REDACTED:phone]"
    assert {f.kind for f in kinds} == {"phone"}


def test_phone_con_prefijo_o_sufijo_sigue_redactado_como_en_main():
    # Regresión del primer arreglo (lookarounds genéricos): estos se escapaban.
    casos = {
        "cliente tel-0991 2345": "cliente tel-[REDACTED:phone]",
        "WA-+593991234567": "WA-[REDACTED:phone]",
        "llamar +593991234567-ext": "llamar [REDACTED:phone]-ext",
        "phone-555-1234": "phone-[REDACTED:phone]",
        "+593991234567-1": "[REDACTED:phone]-1",
    }
    for entrada, esperado in casos.items():
        redacted, kinds = redact_text(entrada)
        assert redacted == esperado, entrada
        assert "phone" in {f.kind for f in kinds}, entrada


def test_ids_de_respuesta_igual_que_en_main():
    # Sin empeorar ni «arreglar» por accidente: la excepción es solo para CVE.
    redacted, _ = redact_text("chatcmpl-01a19d80-1234-5678-8ea5-abd08b2a7252")
    assert redacted == "chatcmpl-01a19d80-[REDACTED:phone]-8ea5-abd08b2a7252"


def test_marcador_interno_en_la_entrada_no_rompe_la_redaccion():
    redacted, _ = redact_text("\ue0000\ue000 CVE-2026-1234 +593991234567")
    assert "+593991234567" not in redacted


def test_phone_sigue_redactando_telefonos():
    for tel in ("+593 99 123 4567", "099 123 4567", "(02) 234-5678", "+593991112233", "2345-6789"):
        redacted, kinds = redact_text(f"llamar al {tel}.")
        assert tel not in redacted, tel
        assert "phone" in {f.kind for f in kinds}, tel


def test_cve_seguido_de_digitos_no_protege_un_telefono():
    # Revisión final (4-nov): forma de CVE seguida de más dígitos se redacta como en main.
    for text in ("CVE-2026-099123 4567", "CVE-2026-12345 6789"):
        assert "[REDACTED:phone]" in redact_text(text)[0], text
    assert redact_text("Parche para CVE-2026-1234 hoy")[0] == "Parche para CVE-2026-1234 hoy"
