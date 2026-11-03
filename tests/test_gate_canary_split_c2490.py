"""C2490 b: el canario partido en varias cadenas o con separadores bloquea.

Cierra rt-gate-canary-split: antes de buscar canarios, el gate analiza
también la concatenación de las cadenas del payload y su forma compacta
(sin espacios ni separadores).
"""

from __future__ import annotations

from shield.gate import check
from shield.gate.canaries import find_canaries_compact


def test_canario_partido_en_lista_bloquea():
    result = check(["CANARY-SHIELD-", "0001"])
    assert result.allowed is False
    assert result.canaries_found == ["CANARY-SHIELD-0001"]


def test_canario_partido_en_argumentos_anidados_bloquea():
    payload = {"messages": [{"content": "CANARY-"}, {"content": "SHIELD-0001"}]}
    assert check(payload).allowed is False


def test_canario_con_espacios_y_saltos_bloquea():
    assert check("dato: CANARY - SHIELD -\n 0001 fin").allowed is False
    assert check({"a": "sk canary shield", "b": "do not leak"}).allowed is False


def test_lista_propia_de_canarios_partida():
    pool = ["CANARY-SHIELD-0007"]
    assert check({"x": "CANARY-SHI", "y": "ELD-0007"}, canaries=pool).allowed is False


def test_canario_corto_no_usa_forma_compacta():
    # '[REDACTED]' es canario en evals/canaries.json: compactado sería
    # 'redacted', palabra común; solo cuenta en forma exacta.
    assert find_canaries_compact("este documento fue redacted ayer", ["[REDACTED]"]) == []
    assert check("documento redacted", canaries=["[REDACTED]"]).allowed is True


def test_texto_limpio_no_bloquea():
    payload = {"messages": [{"content": "Factura 0001 de CANARIAS SHIELD S.A."}]}
    assert check(payload).allowed is True
