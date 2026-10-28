"""Uso raro por agente o llave, con estadística simple (H5 lo completa)."""

from __future__ import annotations

from shield.schemas import CallLog


def flag_anomalies(logs: list[CallLog], *, spike_factor: float = 5.0) -> list[CallLog]:
    """Marca picos de costo contra la mediana del propio agente. Stub de H1."""
    if not logs:
        return []
    costs = sorted(log.cost_usd for log in logs)
    median = costs[len(costs) // 2] or 0.0
    if median <= 0:
        return []
    return [log for log in logs if log.cost_usd > median * spike_factor]
