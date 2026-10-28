"""Agente de Bodega: SAM 3.1 + voz vía ``@shield.tool`` (token propio).

- ``count_stock`` (read): imagen o video con track IDs, un pedido SAM por
  concepto (doc oficial: un concepto por request).
- ``transcribe`` (read): Voice -> ``[{item, qty, unit}]``.
- ``diff_stock`` (read): contado contra el **teórico** del ledger de
  Compras (stock según compras registradas). No muta el inventario.
"""

from __future__ import annotations

from typing import Any

from crew.bodega.sam import SamFn
from crew.bodega.sam import count_stock as _count_stock
from crew.bodega.voice import transcribe as _transcribe
from crew.compras.ledger import Ledger
from shield.meta_client import MetaClient
from shield.policy.check import PolicyEngine
from shield.sdk.pending import PendingRegistry, default_registry
from shield.sdk.tool import tool


class BodegaAgent:
    agent_name = "bodega"

    def __init__(
        self,
        ledger: Ledger | None = None,
        *,
        meta_client: MetaClient | None = None,
        sam_fn: SamFn | None = None,
        engine: PolicyEngine | None = None,
        registry: PendingRegistry | None = None,
    ) -> None:
        self.ledger = ledger
        self.meta_client = meta_client
        self.sam_fn = sam_fn
        self.token: str | None = None  # token Shield propio (shd_bodega_...)
        engine = engine or PolicyEngine()
        registry = registry or default_registry

        @tool(effect="read", agent="bodega", engine=engine, registry=registry, name="count_stock")
        def _count(
            media: dict[str, Any], prompts: list[str], _sources=None, source_doc_ids=None
        ) -> dict[str, Any]:
            clean_media = {k: v for k, v in dict(media).items() if k != "sam_output_text"}
            return _count_stock(
                clean_media, list(prompts), sam_fn=self.sam_fn, meta_client=self.meta_client
            )

        @tool(effect="read", agent="bodega", engine=engine, registry=registry, name="transcribe")
        def _voice(audio_text: str, _sources=None, source_doc_ids=None) -> dict[str, Any]:
            return _transcribe(audio_text, meta_client=self.meta_client)

        @tool(effect="read", agent="bodega", engine=engine, registry=registry, name="diff_stock")
        def _diff(counts: dict[str, float], _sources=None, source_doc_ids=None) -> dict[str, Any]:
            return self._diff_impl(dict(counts))

        self._count_tool = _count
        self._voice_tool = _voice
        self._diff_tool = _diff

    def _diff_impl(self, counts: dict[str, float]) -> dict[str, Any]:
        if self.ledger is None:
            raise ValueError("diff_stock requiere el ledger de Compras (teórico)")
        rows: list[dict[str, Any]] = []
        for sku, counted in sorted(counts.items()):
            theoretical = self.ledger.theoretical_stock(str(sku))
            diff = float(counted) - theoretical
            rows.append(
                {
                    "item": str(sku),
                    "theoretical": theoretical,
                    "counted": float(counted),
                    "diff": diff,
                    "status": "ok" if diff == 0 else ("faltante" if diff < 0 else "sobrante"),
                }
            )
        return {"rows": rows, "has_diff": any(r["diff"] != 0 for r in rows)}

    # -- API pública (pasa por la política vía @shield.tool) ---------------
    def count_stock(
        self, media: dict[str, Any], prompts: list[str], *, sources: list[Any] | None = None
    ) -> dict[str, Any]:
        if sources:
            return self._count_tool(media=dict(media), prompts=list(prompts), _sources=sources)
        return self._count_tool(media=dict(media), prompts=list(prompts))

    def transcribe(self, audio_or_text: Any, *, sources: list[Any] | None = None) -> dict[str, Any]:
        # Archivos reales van directo a Voice; el texto replay pasa por tool.
        from pathlib import Path

        if isinstance(audio_or_text, Path) or (
            isinstance(audio_or_text, str) and Path(audio_or_text).is_file()
        ):
            return _transcribe(audio_or_text, meta_client=self.meta_client)
        if sources:
            return self._voice_tool(audio_text=str(audio_or_text), _sources=sources)
        return self._voice_tool(audio_text=str(audio_or_text))

    def diff_stock(
        self, counts: dict[str, float], *, sources: list[Any] | None = None
    ) -> dict[str, Any]:
        if sources:
            return self._diff_tool(counts=dict(counts), _sources=sources)
        return self._diff_tool(counts=dict(counts))
