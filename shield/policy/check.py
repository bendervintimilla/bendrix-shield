"""check(agent, tool, args, sources) -> PolicyDecision.

Orden: 1) reglas deterministas YAML, 2) inyección en fuentes no confiables,
3) campos sensibles y límites, 4) Spark 1.3 solo para lo ambiguo.
Con ``spark_review=True``: Spark por documento no confiable (caché por
(herramienta, hash del texto); los fallos no se cachean) y gana la
decisión más estricta (block > ask_owner > allow).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from shield.policy.injection import UntrustedDoc, scan_sources
from shield.policy.rules import amount_in, load_policy, sensitive_fields_in
from shield.policy.spark import Classifier, is_spark_failure, make_spark_classifier
from shield.schemas import Decision, PolicyDecision

_STRICT = {Decision.ALLOW: 0, Decision.ASK_OWNER: 1, Decision.BLOCK: 2}
_ENV_ON = {"on", "1", "true", "yes"}


def spark_review_enabled() -> bool:
    """True si SHIELD_SPARK_REVIEW está encendido (on/1/true/yes)."""
    return os.environ.get("SHIELD_SPARK_REVIEW", "").strip().lower() in _ENV_ON


def _source_text(source: Any) -> str:
    if isinstance(source, str):
        return source
    text = getattr(source, "text", None)
    return text if isinstance(text, str) else ""


class PolicyEngine:
    def __init__(
        self,
        *,
        policies_dir: Path | None = None,
        classifier: Classifier | None = None,
        use_spark: bool = False,
        spark_review: bool | None = None,
    ) -> None:
        self.policies_dir = policies_dir
        self._classifier = classifier
        self.use_spark = use_spark or classifier is not None
        # Apagado por defecto; SHIELD_SPARK_REVIEW=on lo activa si no se
        # pasa un valor explícito.
        self.spark_review = spark_review_enabled() if spark_review is None else bool(spark_review)
        self.classifier_calls = 0
        self.spark_review_calls = 0
        self.spark_review_failures = 0
        self.spark_calls = 0
        self.classifier_cost_usd = 0.0
        self._spark_cache: dict[tuple[str, str], PolicyDecision] = {}

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
        deterministic = self._check_deterministic(agent, tool, args, sources, effect=effect)
        if not self.spark_review or deterministic.decision is Decision.BLOCK:
            return deterministic
        return self._apply_spark_review(deterministic, agent, tool, args, sources)

    def _apply_spark_review(
        self,
        deterministic: PolicyDecision,
        agent: str,
        tool: str,
        args: dict[str, Any] | None,
        sources: list[Any] | tuple[Any, ...] | None,
    ) -> PolicyDecision:
        texts = [t for t in (_source_text(s) for s in (sources or [])) if t.strip()]
        if not texts:
            return deterministic
        best: PolicyDecision | None = None
        failed = False
        for text in texts:
            key = (tool, hashlib.sha256(text.encode("utf-8")).hexdigest())
            if key in self._spark_cache:
                cached = self._spark_cache[key]
                if best is None or _STRICT[cached.decision] > _STRICT[best.decision]:
                    best = cached
                continue
            self.classifier_calls += 1
            self.spark_review_calls += 1
            self.spark_calls += 1
            try:
                result = self.classifier(
                    agent=agent, tool=tool, args=dict(args or {}), sources_text=text
                )
            except Exception:
                result = None
            if result is None or is_spark_failure(result):
                # Sin caché: un fallo temporal se reintenta en la
                # siguiente revisión.
                self.spark_review_failures += 1
                failed = True
                continue
            self._spark_cache[key] = result
            if best is None or _STRICT[result.decision] > _STRICT[best.decision]:
                best = result
        if best is not None and _STRICT[best.decision] > _STRICT[deterministic.decision]:
            evidence = list(deterministic.evidence) + list(best.evidence)
            if failed:
                evidence.append("spark_unavailable")
            return PolicyDecision(decision=best.decision, reason=best.reason, evidence=evidence)
        if failed:
            return PolicyDecision(
                decision=deterministic.decision,
                reason=deterministic.reason,
                evidence=list(deterministic.evidence) + ["spark_unavailable"],
            )
        return deterministic

    def _check_deterministic(
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
        if scan.strong and any(h.kind.startswith("reveal_secret") for h in scan.strong):
            return PolicyDecision(
                decision=Decision.BLOCK,
                reason="documento no confiable pide revelar un secreto",
                evidence=[h.evidence() for h in scan.strong],
            )
        # Lectura que pide revelar un secreto por sus propios argumentos:
        # ninguna lectura pasa en silencio si expone llave/token/credencial.
        _secret_marks = (
            "apikey",
            "key",
            "llave",
            "chave",
            "clave",
            "secret",
            "secreto",
            "segredo",
            "token",
            "password",
            "credential",
            "credencial",
        )
        secret_args = [
            s
            for s in sensitive
            if any(m in "".join(c for c in s.lower() if c.isalnum()) for m in _secret_marks)
        ]
        if secret_args and tool_effect == "read":
            return PolicyDecision(
                decision=Decision.BLOCK,
                reason="lectura que llevaría a revelar un secreto, llave o token",
                evidence=[f"field:{s}" for s in secret_args],
            )
        args_scan = scan_sources([str(v) for v in args.values() if isinstance(v, str) and v])
        if any(h.kind.startswith("reveal_secret") for h in args_scan.strong):
            return PolicyDecision(
                decision=Decision.BLOCK,
                reason="los argumentos piden revelar un secreto, llave o token",
                evidence=[h.evidence() for h in args_scan.strong],
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
        # Con spark_review la llamada la hace la revisión por documento.
        if scan.suspicious and tool_effect == "write":
            if self.use_spark and not self.spark_review:
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
