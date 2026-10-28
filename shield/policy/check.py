"""check(agent, tool, args, sources) -> PolicyDecision.

Orden: 1) reglas deterministas YAML, 2) inyección en fuentes no confiables,
3) campos sensibles y límites, 4) Spark 1.3 solo para lo ambiguo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shield.policy.injection import UntrustedDoc, scan_sources
from shield.policy.rules import amount_in, load_policy, sensitive_fields_in
from shield.policy.spark import Classifier, make_spark_classifier
from shield.schemas import Decision, PolicyDecision


class PolicyEngine:
    def __init__(
        self,
        *,
        policies_dir: Path | None = None,
        classifier: Classifier | None = None,
        use_spark: bool = False,
    ) -> None:
        self.policies_dir = policies_dir
        self._classifier = classifier
        self.use_spark = use_spark or classifier is not None
        self.classifier_calls = 0
        self.classifier_cost_usd = 0.0

    @property
    def classifier(self) -> Classifier:
        if self._classifier is None:
            self._classifier = make_spark_classifier()
        return self._classifier

    def check(
        self,
        agent: str,
        tool: str,
        args: dict[str, Any] | None = None,
        sources: list[Any] | tuple[Any, ...] | None = None,
        *,
        effect: str | None = None,
    ) -> PolicyDecision:
        args = dict(args or {})
        sources = list(sources or [])
        policy = load_policy(agent, self.policies_dir)
        if policy is None:
            # Sin YAML cae a `default` si existe; si no, denegar es lo seguro.
            policy = load_policy("default", self.policies_dir)
            if policy is None:
                return PolicyDecision(
                    decision=Decision.BLOCK,
                    reason=f"sin política para el agente {agent!r}",
                    evidence=[f"agent:{agent}"],
                )
        rule = policy.tools.get(tool)
        if rule is None:
            return PolicyDecision(
                decision=Decision.BLOCK,
                reason=f"herramienta no permitida para {agent}: {tool}",
                evidence=[f"tool:{tool}", f"agent:{agent}"],
            )
        tool_effect = effect or rule.effect
        declared = list(policy.sensitive_fields) + list(rule.sensitive_fields)
        sensitive = sensitive_fields_in(args, declared)
        has_untrusted = any(isinstance(s, UntrustedDoc) for s in sources) or bool(sources)
        scan = scan_sources(sources)

        # Inyección fuerte + acción con efecto o campo sensible -> block.
        if scan.strong and (tool_effect == "write" or sensitive):
            return PolicyDecision(
                decision=Decision.BLOCK,
                reason="inyección en documento no confiable deriva en acción con efecto",
                evidence=[h.evidence() for h in scan.strong],
            )
        # Inyección fuerte incluso en lectura que pide revelar secretos.
        if scan.strong and any(h.kind == "reveal_secret" for h in scan.strong):
            return PolicyDecision(
                decision=Decision.BLOCK,
                reason="documento no confiable pide revelar un secreto",
                evidence=[h.evidence() for h in scan.strong],
            )
        if sensitive and tool_effect == "write":
            if has_untrusted and scan.hits:
                return PolicyDecision(
                    decision=Decision.BLOCK,
                    reason="cambio de campo sensible derivado de fuente no confiable sospechosa",
                    evidence=[h.evidence() for h in scan.hits] + [f"field:{s}" for s in sensitive],
                )
            if policy.asks("sensitive_change"):
                return PolicyDecision(
                    decision=Decision.ASK_OWNER,
                    reason="cambio de campo sensible requiere aprobación del dueño",
                    evidence=[f"field:{s}" for s in sensitive],
                )
            return PolicyDecision(
                decision=Decision.BLOCK,
                reason="cambio de campo sensible no autorizado por la política",
                evidence=[f"field:{s}" for s in sensitive],
            )
        amount = amount_in(args)
        if (
            amount is not None
            and policy.max_amount_usd is not None
            and tool_effect == "write"
            and amount > policy.max_amount_usd
        ):
            if policy.asks("amount_over_limit"):
                return PolicyDecision(
                    decision=Decision.ASK_OWNER,
                    reason=f"monto {amount} supera el límite {policy.max_amount_usd}",
                    evidence=[f"amount:{amount}", f"limit:{policy.max_amount_usd}"],
                )
            return PolicyDecision(
                decision=Decision.BLOCK,
                reason=f"monto {amount} supera el límite {policy.max_amount_usd}",
                evidence=[f"amount:{amount}", f"limit:{policy.max_amount_usd}"],
            )
        # Ambiguo: señales débiles combinadas en un write -> Spark (o ask_owner).
        if scan.suspicious and tool_effect == "write":
            if self.use_spark:
                self.classifier_calls += 1
                sources_text = "\n".join(getattr(s, "text", str(s)) for s in sources)
                return self.classifier(agent=agent, tool=tool, args=args, sources_text=sources_text)
            return PolicyDecision(
                decision=Decision.ASK_OWNER,
                reason="fuente sospechosa sin clasificador: se escala al dueño",
                evidence=[h.evidence() for h in scan.weak],
            )
        if tool_effect == "write" and has_untrusted and policy.asks("write_from_untrusted"):
            if sources:
                return PolicyDecision(
                    decision=Decision.ASK_OWNER,
                    reason="acción con efecto derivada de fuente no confiable: confirmar",
                    evidence=[f"source:{getattr(s, 'doc_id', 'inline')}" for s in sources],
                )
        return PolicyDecision(
            decision=Decision.ALLOW,
            reason="reglas deterministas: permitido",
            evidence=[f"tool:{tool}", f"effect:{tool_effect}"],
        )


_default_engine = PolicyEngine()


def check(
    agent: str,
    tool: str,
    args: dict[str, Any] | None = None,
    sources: list[Any] | tuple[Any, ...] | None = None,
    *,
    effect: str | None = None,
    engine: PolicyEngine | None = None,
) -> PolicyDecision:
    return (engine or _default_engine).check(agent, tool, args, sources, effect=effect)
