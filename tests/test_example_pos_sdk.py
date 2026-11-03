"""El ejemplo POS: emitir factura pasa; anular se bloquea; cambiar cuenta pide aprobación."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from shield.sdk import PolicyBlocked, PolicyPending

RUN = Path(__file__).resolve().parents[1] / "examples" / "pos-sdk" / "run.py"


@pytest.fixture()
def pos():
    spec = importlib.util.spec_from_file_location("pos_sdk_run", RUN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_emitir_factura_permitido(pos):
    assert pos.emitir_factura(cliente="Consumidor final", total=12.5).startswith("factura emitida")


def test_anular_factura_bloqueado(pos):
    with pytest.raises(PolicyBlocked):
        pos.anular_factura(numero="DEMO-0001")


def test_cambiar_cuenta_requiere_aprobacion(pos):
    with pytest.raises(PolicyPending) as exc:
        pos.cambiar_cuenta_proveedor(proveedor="Demo", cuenta_bancaria="EC00-DEMO")
    pending = exc.value.pending
    assert pending.status == "pending"
    assert pos.pendientes.approve(pending.pending_id) == "cuenta de Demo cambiada"


def test_factura_sobre_el_limite_pide_aprobacion(pos):
    with pytest.raises(PolicyPending):
        pos.emitir_factura(cliente="Consumidor final", total=5000.0)
