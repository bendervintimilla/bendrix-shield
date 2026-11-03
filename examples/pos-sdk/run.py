"""Agente de punto de venta con NoKey: factura sí; anular o cambiar cuenta no.

Uso: ``uv run python examples/pos-sdk/run.py`` (sin red, sin llaves, datos de juguete).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import shield  # noqa: E402
from shield.policy.check import PolicyEngine  # noqa: E402
from shield.sdk import PendingRegistry, PolicyBlocked, PolicyPending  # noqa: E402

engine = PolicyEngine(policies_dir=Path(__file__).parent / "policies", spark_review=False)
pendientes = PendingRegistry()
caja = {"engine": engine, "registry": pendientes, "agent": "caja"}


@shield.tool(effect="write", **caja)
def emitir_factura(cliente: str, total: float) -> str:
    return f"factura emitida a {cliente} por {total:.2f}"


@shield.tool(effect="write", **caja)
def anular_factura(numero: str) -> str:
    return f"factura {numero} anulada"


@shield.tool(effect="write", **caja)
def cambiar_cuenta_proveedor(proveedor: str, cuenta_bancaria: str) -> str:
    return f"cuenta de {proveedor} cambiada"


def intentar(nombre: str, fn, **kwargs) -> str:
    try:
        return f"{nombre}: allow -> {fn(**kwargs)}"
    except PolicyBlocked as exc:
        return f"{nombre}: block -> {exc.decision.reason}"
    except PolicyPending as exc:
        return f"{nombre}: ask_owner -> {exc.pending.pending_id} espera al dueño"


if __name__ == "__main__":
    print(intentar("emitir", emitir_factura, cliente="Consumidor final", total=12.5))
    print(intentar("anular", anular_factura, numero="DEMO-0001"))
    cuenta = {"proveedor": "Demo", "cuenta_bancaria": "EC00-DEMO"}
    print(intentar("cuenta", cambiar_cuenta_proveedor, **cuenta))
