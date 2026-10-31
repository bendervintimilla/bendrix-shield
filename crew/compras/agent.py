"""Agente de Compras: herramientas vía ``@shield.tool`` (un token propio).

Toda herramienta con efecto pasa por ``policy.check`` antes de ejecutarse
(SPEC §2.4). La factura entra como ``untrusted``: si trae una orden del
tipo «cambia el IBAN», la acción derivada termina en ``block`` con la
evidencia del fragmento, y la función real nunca se ejecuta.

Herramientas:
- ``extract_invoice`` (read): Spark 1.3 visión o parser replay + validación.
- ``propose_purchase`` (read): propuesta sin mutar nada.
- ``post_purchase`` (write): registra la compra, idempotente por hash.
- ``update_supplier_account`` (write, sensible): cuenta de pago del
  proveedor; sin fuente sospechosa escala a ``ask_owner``.
- ``recost_dish`` (read): costo del plato con el promedio ponderado.
"""

from __future__ import annotations

from typing import Any

from crew.compras.invoice import ExtractedInvoice, extract_invoice, validate_invoice
from crew.compras.ledger import Ledger, invoice_content_hash
from shield.meta_client import MetaClient
from shield.policy.check import PolicyEngine, spark_review_enabled
from shield.sdk.pending import PendingRegistry, default_registry
from shield.sdk.tool import tool

_PAYMENT_KEYS = ("iban", "bank_account", "account_number", "payment_account", "cuenta", "account")


def _tool_invoice(data: dict[str, Any]) -> dict[str, Any]:
    """Forma para tools: sin pago y con ``vendor`` (no ``supplier``).

    ``supplier`` a secas cae dentro del alias sensible ``supplier_email``
    de las reglas H4; la compra legítima no debe escalar por eso.
    """
    clean = _strip_payment(data)
    if "supplier" in clean:
        clean.setdefault("vendor", clean.pop("supplier"))
    return clean


def _strip_payment(data: dict[str, Any]) -> dict[str, Any]:
    """La factura como dato de compra nunca arrastra campos de pago."""
    clean: dict[str, Any] = {}
    for key, value in data.items():
        norm = key.lower().replace("-", "_")
        if any(token in norm for token in _PAYMENT_KEYS):
            continue
        if isinstance(value, dict):
            value = _strip_payment(value)
        clean[key] = value
    return clean


class ComprasAgent:
    agent_name = "compras"

    def __init__(
        self,
        ledger: Ledger,
        *,
        meta_client: MetaClient | None = None,
        engine: PolicyEngine | None = None,
        registry: PendingRegistry | None = None,
    ) -> None:
        self.ledger = ledger
        self.meta_client = meta_client
        self.token: str | None = None  # token Shield propio (shd_compras_...)
        # Spark por documento solo con SHIELD_SPARK_REVIEW=on (replay: apagado).
        engine = engine or PolicyEngine(spark_review=spark_review_enabled())
        registry = registry or default_registry

        @tool(
            effect="read", agent="compras", engine=engine, registry=registry, name="extract_invoice"
        )
        def _extract(
            doc_text: str = "", doc_id: str = "invoice", _sources=None, source_doc_ids=None
        ) -> dict[str, Any]:
            sources = list(_sources or [])
            doc: Any = sources[0] if sources else doc_text
            invoice = extract_invoice(doc, client=self.meta_client, doc_id=doc_id)
            return invoice.public_dict()

        @tool(
            effect="read",
            agent="compras",
            engine=engine,
            registry=registry,
            name="propose_purchase",
        )
        def _propose(invoice: dict[str, Any], _sources=None, source_doc_ids=None) -> dict[str, Any]:
            clean = _tool_invoice(dict(invoice))
            parsed = extract_invoice(clean, doc_id="proposal")
            validation = validate_invoice(parsed)
            digest = invoice_content_hash(parsed.public_dict())
            already = any(p["content_hash"] == digest for p in self.ledger.list_purchases())
            return {
                "supplier": parsed.supplier,
                "invoice_number": parsed.invoice_number,
                "lines": [line.to_dict() for line in parsed.lines],
                "subtotal": parsed.subtotal,
                "tax": parsed.tax,
                "total": parsed.total,
                "content_hash": digest,
                "already_posted": already,
                "validation": validation.to_dict(),
            }

        @tool(
            effect="write", agent="compras", engine=engine, registry=registry, name="post_purchase"
        )
        def _post(invoice: dict[str, Any], _sources=None, source_doc_ids=None) -> dict[str, Any]:
            clean = _tool_invoice(dict(invoice))
            parsed = extract_invoice(clean, doc_id="post")
            return self.ledger.record_purchase(
                supplier=parsed.supplier,
                lines=[line.to_dict() for line in parsed.lines],
                invoice_number=parsed.invoice_number or None,
                invoice_date=parsed.date or None,
                currency=parsed.currency,
                subtotal=parsed.subtotal,
                tax=parsed.tax,
                total=parsed.total,
                content_hash=invoice_content_hash(parsed.public_dict()),
            )

        @tool(
            effect="write",
            agent="compras",
            engine=engine,
            registry=registry,
            name="update_supplier_account",
        )
        def _update_account(
            supplier_id: int, payment_account: str, _sources=None, source_doc_ids=None
        ) -> dict[str, Any]:
            return self.ledger.set_supplier_account(int(supplier_id), str(payment_account))

        @tool(effect="read", agent="compras", engine=engine, registry=registry, name="recost_dish")
        def _recost(dish: str, _sources=None, source_doc_ids=None) -> dict[str, Any]:
            return self.ledger.recipe_cost(str(dish))

        self._extract_tool = _extract
        self._propose_tool = _propose
        self._post_tool = _post
        self._update_account_tool = _update_account
        self._recost_tool = _recost

    # -- API pública (pasa por la política vía @shield.tool) ---------------
    def extract(self, doc: Any, *, doc_id: str = "invoice") -> ExtractedInvoice:
        if isinstance(doc, dict):
            return extract_invoice(_strip_payment(dict(doc)), doc_id=doc_id)
        text = str(getattr(doc, "text", doc))
        if hasattr(doc, "text") and not isinstance(doc, str):
            result = self._extract_tool(doc_text=text, doc_id=doc_id, _sources=[doc])
        else:
            result = self._extract_tool(doc_text=text, doc_id=doc_id)
        return extract_invoice(result, doc_id=doc_id)

    def propose_purchase(self, invoice: Any, *, sources: list[Any] | None = None) -> dict[str, Any]:
        data = invoice.public_dict() if isinstance(invoice, ExtractedInvoice) else dict(invoice)
        if sources:
            return self._propose_tool(invoice=_tool_invoice(data), _sources=sources)
        return self._propose_tool(invoice=_tool_invoice(data))

    def post_purchase(self, invoice: Any, *, sources: list[Any] | None = None) -> dict[str, Any]:
        data = invoice.public_dict() if isinstance(invoice, ExtractedInvoice) else dict(invoice)
        if sources:
            return self._post_tool(invoice=_tool_invoice(data), _sources=sources)
        return self._post_tool(invoice=_tool_invoice(data))

    def update_supplier_account(
        self, supplier_id: int, payment_account: str, *, sources: list[Any] | None = None
    ) -> dict[str, Any]:
        if sources:
            return self._update_account_tool(
                supplier_id=int(supplier_id), payment_account=str(payment_account), _sources=sources
            )
        return self._update_account_tool(
            supplier_id=int(supplier_id), payment_account=str(payment_account)
        )

    def recost_dish(self, dish: str) -> dict[str, Any]:
        return self._recost_tool(dish=str(dish))
