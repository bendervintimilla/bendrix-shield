"""Uso raro por agente o llave, con estadística simple.

Sobre los CallLog del gateway (y las series de evals/usage/): país nuevo,
modelo que el agente no usa, pico de costo contra su propia mediana, pico
de volumen y ráfaga de bloqueos. ``flag_anomalies`` se conserva: la
función rica es ``detect_anomalies`` con baseline explícito o inferido.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shield.schemas import CallLog


@dataclass(frozen=True)
class AnomalyFinding:
    agent: str
    kind: str  # new_country | new_model | cost_spike | volume_spike | blocked_burst
    detail: str
    severity: str  # high | medium | low
    count: int = 1
    evidence: list[str] = field(default_factory=list)


def _median_cost(logs: list[CallLog]) -> float:
    costs = [log.cost_usd for log in logs if log.cost_usd > 0]
    return float(statistics.median(costs)) if costs else 0.0


def flag_anomalies(logs: list[CallLog], *, spike_factor: float = 5.0) -> list[CallLog]:
    """Marca picos de costo contra la mediana del propio agente."""
    if not logs:
        return []
    costs = sorted(log.cost_usd for log in logs)
    median = costs[len(costs) // 2] or 0.0
    if median <= 0:
        return []
    return [log for log in logs if log.cost_usd > median * spike_factor]


def _split_baseline(logs: list[CallLog]) -> tuple[list[CallLog], list[CallLog]]:
    ordered = sorted(logs, key=lambda log: log.ts)
    if len(ordered) < 4:
        return ordered, ordered
    cut = max(1, len(ordered) // 2)
    return ordered[:cut], ordered[cut:]


def is_anomalous_call(
    log: CallLog,
    baseline: list[CallLog],
    *,
    spike_factor: float = 5.0,
) -> list[str]:
    """Razones por las que una llamada se sale del baseline de su agente."""
    own = [b for b in baseline if b.agent == log.agent] or baseline
    reasons: list[str] = []
    countries = {b.src_country for b in own if b.src_country}
    if log.src_country and countries and log.src_country not in countries:
        reasons.append(f"new_country:{log.src_country}")
    models = {b.model for b in own if b.model}
    if models and log.model not in models:
        reasons.append(f"new_model:{log.model}")
    median = _median_cost(own)
    if median > 0 and log.cost_usd > median * spike_factor:
        reasons.append(f"cost_spike:{log.cost_usd}>{median * spike_factor:.2f}")
    return reasons


def flagged_logs(
    logs: list[CallLog],
    baseline: list[CallLog] | None = None,
    *,
    spike_factor: float = 5.0,
) -> list[CallLog]:
    base, target = (baseline, list(logs)) if baseline is not None else _split_baseline(logs)
    if baseline is not None:
        target = list(logs)
    return [log for log in target if is_anomalous_call(log, base, spike_factor=spike_factor)]


def detect_anomalies(
    logs: list[CallLog],
    baseline: list[CallLog] | None = None,
    *,
    spike_factor: float = 5.0,
) -> list[AnomalyFinding]:
    """Findings agrupados por agente y tipo, con evidencia contable."""
    if not logs:
        return []
    base, target = (list(baseline), list(logs)) if baseline is not None else _split_baseline(logs)
    findings: list[AnomalyFinding] = []
    agents = sorted({log.agent for log in target})
    for agent in agents:
        own_base = [b for b in base if b.agent == agent] or base
        own = [log for log in target if log.agent == agent]
        countries: dict[str, list[CallLog]] = {}
        models: dict[str, list[CallLog]] = {}
        spikes: list[CallLog] = []
        for log in own:
            reasons = is_anomalous_call(log, own_base, spike_factor=spike_factor)
            for reason in reasons:
                kind, _, value = reason.partition(":")
                if kind == "new_country":
                    countries.setdefault(value, []).append(log)
                elif kind == "new_model":
                    models.setdefault(value, []).append(log)
                elif kind == "cost_spike":
                    spikes.append(log)
        for country, hits in sorted(countries.items()):
            findings.append(
                AnomalyFinding(
                    agent=agent,
                    kind="new_country",
                    detail=f"llamadas desde un país nuevo para {agent}: {country}",
                    severity="high" if len(hits) >= 3 else "medium",
                    count=len(hits),
                    evidence=[
                        f"country:{country}",
                        f"calls:{len(hits)}",
                        f"first:{hits[0].ts.isoformat()}",
                    ],
                )
            )
        for model, hits in sorted(models.items()):
            findings.append(
                AnomalyFinding(
                    agent=agent,
                    kind="new_model",
                    detail=f"modelo que {agent} no usa en su baseline: {model}",
                    severity="high" if len(hits) >= 3 else "medium",
                    count=len(hits),
                    evidence=[f"model:{model}", f"calls:{len(hits)}"],
                )
            )
        if spikes:
            findings.append(
                AnomalyFinding(
                    agent=agent,
                    kind="cost_spike",
                    detail=f"costo por llamada muy sobre la mediana de {agent}",
                    severity="high",
                    count=len(spikes),
                    evidence=[
                        f"max_cost:{max(s.cost_usd for s in spikes)}",
                        f"median:{_median_cost(own_base)}",
                    ],
                )
            )
        blocked = [
            log for log in own if str(log.decision) == "block" or log.decision.value == "block"
        ]
        if len(blocked) >= 3:
            findings.append(
                AnomalyFinding(
                    agent=agent,
                    kind="blocked_burst",
                    detail=f"ráfaga de llamadas bloqueadas de {agent}",
                    severity="medium",
                    count=len(blocked),
                    evidence=[f"blocked:{len(blocked)}"],
                )
            )
        # Pico de volumen: tasa por hora muy sobre el baseline.
        if own_base and own:
            base_hours = max(
                (max(b.ts for b in own_base) - min(b.ts for b in own_base)).total_seconds() / 3600,
                1.0,
            )
            target_hours = max(
                (max(b.ts for b in own) - min(b.ts for b in own)).total_seconds() / 3600, 1.0
            )
            base_rate = len(own_base) / base_hours
            target_rate = len(own) / target_hours
            if base_rate > 0 and target_rate > base_rate * 3 and len(own) >= 10:
                findings.append(
                    AnomalyFinding(
                        agent=agent,
                        kind="volume_spike",
                        detail=f"volumen por hora de {agent}: {target_rate:.1f} vs {base_rate:.1f}",
                        severity="medium",
                        count=len(own),
                        evidence=[f"rate:{target_rate:.2f}/h", f"baseline:{base_rate:.2f}/h"],
                    )
                )
    return findings


def load_usage_file(path: str | Path) -> tuple[list[CallLog], dict[str, Any]]:
    """Lee una serie de evals/usage/*.json como CallLog + metadatos."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    logs = [CallLog.model_validate(call) for call in data.get("calls") or []]
    meta = {k: v for k, v in data.items() if k != "calls"}
    return logs, meta
