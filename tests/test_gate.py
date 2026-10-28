import pytest

from shield.gate import check
from shield.gate.check import GateBlocked, check_or_raise


def test_clean_payload_allowed():
    result = check({"model": "muse-spark-1.3", "messages": [{"content": "hola"}]})
    assert result.allowed is True
    assert result.canaries_found == []


def test_canary_blocked():
    result = check({"text": "la llave es CANARY-SHIELD-0001"})
    assert result.allowed is False
    assert "CANARY-SHIELD-0001" in result.canaries_found


def test_check_or_raise():
    with pytest.raises(GateBlocked):
        check_or_raise("sk-canary-shield-do-not-leak")
    check_or_raise("texto limpio")


def test_custom_canaries():
    assert check("secreto-x", canaries=["secreto-x"]).allowed is False
    assert check("secreto-x").allowed is True
