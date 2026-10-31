"""El agente guardián: orquesta watch/estate/exposure/anomaly/actions (H5).

Tool calling con Spark 1.3 cuando hay cliente; sin créditos cae al pipeline
determinista (mismas herramientas, sin modelo). Las acciones con efecto son
una interfaz (``GuardianActions``): ``RegistryActions`` es el adaptador
local de demo y ``RunbookGuardianActions`` (H8) delega en los runbooks
reales de H6 (``shield/actions/``) por el mismo camino. Ninguna acción con
efecto se ejecuta sin un ``approval_id`` emitido por ``ask_owner`` en esta
misma corrida: rotar o revocar sin OK del dueño no es una ruta válida.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from shield.anomaly import AnomalyFinding, detect_anomalies
from shield.brand import BRAND
from shield.exposure import match_all, triage_difficult
from shield.notice import NoticeDraft, draft_notice
from shield.schemas import Asset, CallLog, Exposure, ThreatCard

EFFECT_TOOLS = ("rotate_token", "rotate_upstream_key", "revoke")


class GuardianActions(Protocol):
    """Interfaz de acciones con efecto. La implementación real es de H6."""

    def rotate_token(self, agent: str, approval_id: str) -> dict[str, Any]: ...
    def rotate_upstream_key(self, provider: str, approval_id: str) -> dict[str, Any]: ...
    def verify(self, target: str) -> dict[str, Any]: ...
    def revoke(self, token_id: str, approval_id: str) -> dict[str, Any]: ...


class RegistryActions:
    """Adaptador local/demo sobre el Registry (H6 lo reemplaza por runbooks).

    Nunca devuelve el token en claro: solo ids. Rotar un token no toca a
    ningún otro agente (invariante SPEC §2.5, ya garantizado por Registry).
    """

    def __init__(self, registry: Any) -> None:
        self._registry = registry

    def rotate_token(self, agent: str, approval_id: str) -> dict[str, Any]:
        active = [t for t in self._registry.list_tokens(agent) if str(t.status) == "active"]
        if not active:
            return {"status": "not_found", "agent": agent}
        rotated = self._registry.rotate(active[0].token_id)
        if rotated is None:
            return {"status": "not_found", "agent": agent}
        new_token, _raw = rotated  # el valor en claro jamás sale de aquí
        return {"status": "rotated", "agent": agent, "new_token_id": new_token.token_id}

    def rotate_upstream_key(self, provider: str, approval_id: str) -> dict[str, Any]:
        return {
            "status": "manual_step_required",
            "provider": provider,
            "detail": "el proveedor no expone rotación por API aquí; paso manual + verify (H6)",
        }

    def verify(self, target: str) -> dict[str, Any]:
        tokens = self._registry.list_tokens(target)
        active = [t for t in tokens if str(t.status) == "active"]
        return {
            "status": "ok" if active else "no_active_token",
            "target": target,
            "active_tokens": len(active),
        }

    def revoke(self, token_id: str, approval_id: str) -> dict[str, Any]:
        token = self._registry.revoke(token_id)
        return {"status": "revoked" if token else "not_found", "token_id": token_id}


class RunbookGuardianActions:
    """``GuardianActions`` sobre los runbooks reales de H6 (conexión H8).

    Cada método hace plan → apply(approval_id) → verify del runbook. El
    ``approval_id`` es el ``pending_id`` del ``PendingRegistry`` compartido
    con los canales: sin aprobación aprobada, H6 levanta
    ``ApprovalRequired`` y aquí se devuelve ``blocked`` sin efecto.
    Nunca devuelve secretos: solo ids, huellas y estados.
    """

    def __init__(self, actions: Any, *, grace_s: float = 0.0) -> None:
        self._actions = actions
        self.grace_s = grace_s

    def rotate_token(self, agent: str, approval_id: str) -> dict[str, Any]:
        from shield.actions.runbooks import ApprovalRequired

        runbook = self._actions.rotate_token(grace_s=self.grace_s)
        plan = runbook.plan(agent=agent)
        try:
            result = runbook.apply(plan, approval_id=approval_id)
        except ApprovalRequired as exc:
            return {"status": "blocked", "reason": str(exc), "agent": agent}
        except ValueError as exc:
            return {"status": "not_found", "reason": str(exc), "agent": agent}
        verified = runbook.verify(agent=agent)
        return {
            "status": result.status,
            "agent": agent,
            "new_token_id": result.new_token_id,
            "plan_id": result.plan_id,
            "verify_ok": verified.ok,
        }

    def rotate_upstream_key(self, provider: str, approval_id: str) -> dict[str, Any]:
        from shield.actions.runbooks import ApprovalRequired, ManualStepRequired

        try:
            runbook = self._actions.rotate_upstream_key()
            plan = runbook.plan(provider=provider)
            result = runbook.apply(plan, approval_id=approval_id)
        except ManualStepRequired as exc:
            return {"status": "manual_step_required", "provider": provider, "detail": str(exc)}
        except ApprovalRequired as exc:
            return {"status": "blocked", "reason": str(exc), "provider": provider}
        except PermissionError as exc:
            return {"status": "manual_step_required", "provider": provider, "detail": str(exc)}
        return {
            "status": result.status,
            "provider": provider,
            "plan_id": result.plan_id,
            "details": dict(result.details),
        }

    def verify(self, target: str) -> dict[str, Any]:
        runbook = self._actions.verify()
        result = runbook.verify(agents=[target])
        return {"status": "ok" if result.ok else "failed", "target": target, "ok": result.ok}

    def revoke(self, token_id: str, approval_id: str) -> dict[str, Any]:
        from shield.actions.runbooks import ApprovalRequired

        registry = self._actions.registry
        token = registry.get_token(token_id)
        agent = token.agent if token else token_id
        if token is None and not registry.list_tokens(token_id):
            return {"status": "not_found", "token_id": token_id}
        runbook = self._actions.revoke()
        plan = runbook.plan(agent=agent)
        try:
            result = runbook.apply(plan, approval_id=approval_id)
        except ApprovalRequired as exc:
            return {"status": "blocked", "reason": str(exc), "token_id": token_id}
        return {"status": result.status, "agent": agent, "token_id": token_id}


class Approver(Protocol):
    def ask_owner(self, plan: Plan) -> str | None: ...


class SimulatedApprover:
    """Aprobador de demo/tests: aprueba o rechaza sin canal externo (H8)."""

    def __init__(self, approve: bool = True) -> None:
        self.approve = approve
        self.asked: list[Plan] = []

    def ask_owner(self, plan: Plan) -> str | None:
        self.asked.append(plan)
        return f"appr_{uuid.uuid4().hex[:12]}" if self.approve else None


@dataclass
class PlanStep:
    action: str  # rotate_token | rotate_upstream_key | verify | revoke | draft_notice | patch_plan
    target: str
    reason: str
    requires_approval: bool = True


@dataclass
class Plan:
    steps: list[PlanStep] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"summary": self.summary, "steps": [vars(step) for step in self.steps]}


@dataclass
class GuardianReport:
    exposures: list[Exposure] = field(default_factory=list)
    anomalies: list[AnomalyFinding] = field(default_factory=list)
    plan: Plan | None = None
    approval_id: str | None = None
    executed: list[dict[str, Any]] = field(default_factory=list)
    notices: list[NoticeDraft] = field(default_factory=list)
    needs_credits: bool = False
    summary: str = ""


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {"type": "function", "function": {"name": name, "description": desc, "parameters": params}}
    for name, desc, params in [
        (
            "match_exposure",
            "Cruza avisos con el inventario y devuelve exposiciones",
            {"type": "object", "properties": {}},
        ),
        (
            "detect_anomaly",
            "Detecta uso anómalo por agente en los CallLog",
            {"type": "object", "properties": {}},
        ),
        (
            "propose_plan",
            "Propone un plan de contención desde exposiciones y anomalías",
            {"type": "object", "properties": {}},
        ),
        (
            "ask_owner",
            "Pide la aprobación del dueño para el plan propuesto",
            {"type": "object", "properties": {}},
        ),
        (
            "rotate_token",
            "Rota el token Shield de un agente (exige approval_id)",
            {
                "type": "object",
                "properties": {"agent": {"type": "string"}, "approval_id": {"type": "string"}},
                "required": ["agent", "approval_id"],
            },
        ),
        (
            "rotate_upstream_key",
            "Rota la llave del proveedor (exige approval_id)",
            {
                "type": "object",
                "properties": {"provider": {"type": "string"}, "approval_id": {"type": "string"}},
                "required": ["provider", "approval_id"],
            },
        ),
        (
            "verify",
            "Verifica que un agente/servicio sigue sano tras la contención",
            {
                "type": "object",
                "properties": {"target": {"type": "string"}},
                "required": ["target"],
            },
        ),
        (
            "revoke",
            "Revoca un token por id (exige approval_id)",
            {
                "type": "object",
                "properties": {"token_id": {"type": "string"}, "approval_id": {"type": "string"}},
                "required": ["token_id", "approval_id"],
            },
        ),
        (
            "draft_notice",
            "Redacta el borrador RGPD art. 33 / LOPDP del incidente",
            {"type": "object", "properties": {"regime": {"type": "string"}}},
        ),
    ]
]


class GuardianAgent:
    """Guardián con herramientas locales; el modelo solo decide el orden."""

    def __init__(
        self,
        *,
        threats: list[ThreatCard] | None = None,
        assets: list[Asset] | None = None,
        logs: list[CallLog] | None = None,
        baseline: list[CallLog] | None = None,
        actions: GuardianActions | None = None,
        approver: Approver | None = None,
        client: Any | None = None,
        use_wonder_triage: bool = False,
    ) -> None:
        self.threats = list(threats or [])
        self.assets = list(assets or [])
        self.logs = list(logs or [])
        self.baseline = list(baseline) if baseline is not None else None
        self.actions = actions
        self.approver = approver or SimulatedApprover(approve=False)
        self.client = client
        self.use_wonder_triage = use_wonder_triage
        self._exposures: list[Exposure] = []
        self._anomalies: list[AnomalyFinding] = []
        self._plan: Plan | None = None
        self._approval_id: str | None = None
        self._approved_steps: set[tuple[str, str]] = set()

    def set_external_plan(self, steps: list[Any], summary: str = "") -> Plan:
        """Fija un plan propuesto fuera del loop determinista (p. ej. Spark live)."""
        plan_steps: list[PlanStep] = []
        for step in steps or []:
            if isinstance(step, PlanStep):
                plan_steps.append(step)
            elif isinstance(step, dict):
                plan_steps.append(
                    PlanStep(
                        action=str(step.get("action", "")),
                        target=str(step.get("target", "")),
                        reason=str(step.get("reason", "")),
                        requires_approval=bool(step.get("requires_approval", True)),
                    )
                )
        self._plan = Plan(steps=plan_steps, summary=str(summary or ""))
        return self._plan

    # -- herramientas de lectura -------------------------------------------

    def tool_match_exposure(self) -> dict[str, Any]:
        if self.use_wonder_triage:
            result = triage_difficult(self.threats, self.assets, client=self.client)
            self._exposures = result.exposures
            return {
                "exposures": [e.model_dump(mode="json") for e in result.exposures],
                "needs_credits": result.needs_credits,
                "triaged": result.triaged,
            }
        self._exposures = match_all(self.threats, self.assets)
        return {"exposures": [e.model_dump(mode="json") for e in self._exposures]}

    def tool_detect_anomaly(self) -> dict[str, Any]:
        self._anomalies = detect_anomalies(self.logs, self.baseline)
        return {"anomalies": [vars(a) for a in self._anomalies]}

    def tool_propose_plan(self) -> dict[str, Any]:
        steps: list[PlanStep] = []
        seen: set[tuple[str, str]] = set()

        def add(action: str, target: str, reason: str, requires: bool = True) -> None:
            if (action, target) not in seen:
                seen.add((action, target))
                steps.append(PlanStep(action, target, reason, requires))

        asset_by_id = {a.id: a for a in self.assets}
        for exposure in self._exposures:
            if exposure.confidence < 0.8:
                continue  # candidato: lo decide Wonder/humano, no se actúa solo
            asset = asset_by_id.get(exposure.asset_id)
            kind = asset.kind if asset else ""
            if kind in ("shield_token", "gcp_api_key"):
                add(
                    "rotate_token",
                    asset.name if asset else exposure.asset_id,
                    f"exposición {exposure.threat_id}: {exposure.reason}",
                )
            elif kind == "env_vars":
                add(
                    "rotate_upstream_key",
                    asset.platform if asset else "railway",
                    f"exposición {exposure.threat_id}: rotar llaves del proveedor",
                )
                add(
                    "rotate_token",
                    asset.name if asset else exposure.asset_id,
                    "rotar también los tokens Shield del servicio",
                )
            else:
                add(
                    "patch_plan",
                    exposure.asset_id,
                    f"actualizar {exposure.asset_id} por {exposure.threat_id}",
                )
        for anomaly in self._anomalies:
            if anomaly.kind in ("new_country", "new_model", "cost_spike"):
                add("rotate_token", anomaly.agent, f"anomalía {anomaly.kind}: {anomaly.detail}")
        for step in list(steps):
            if step.action in EFFECT_TOOLS:
                add("verify", step.target, f"verificar salud tras {step.action}", requires=False)
        if any(e.confidence >= 0.8 for e in self._exposures) or self._anomalies:
            add(
                "draft_notice",
                "incidente",
                "borrador RGPD/LOPDP para revisión humana",
                requires=False,
            )
        self._plan = Plan(
            steps=steps,
            summary=f"{len(self._exposures)} exposiciones, {len(self._anomalies)} anomalías",
        )
        return self._plan.to_dict()

    def _steps_for(self, approval_id: str) -> set[tuple[str, str]]:
        scoped = getattr(self.approver, "approved_steps_for", None)
        if callable(scoped):
            return set(scoped(approval_id))
        assert self._plan is not None
        return {(s.action, s.target) for s in self._plan.steps if s.requires_approval}

    def tool_ask_owner(self) -> dict[str, Any]:
        if self._plan is None:
            self.tool_propose_plan()
        assert self._plan is not None
        self._approval_id = self.approver.ask_owner(self._plan)
        if self._approval_id:
            self._approved_steps = self._steps_for(self._approval_id)
        pending = getattr(self.approver, "pending_approval_id", None)
        return {
            "approval_id": self._approval_id,
            "approved": self._approval_id is not None,
            "pending_approval_id": pending if not self._approval_id else None,
        }

    def tool_resume_approval(self, approval_id: str) -> dict[str, Any]:
        """Retoma tras la decisión asíncrona del canal (WhatsApp/panel/voz)."""
        if self._plan is None:
            self.tool_propose_plan()
        checker = getattr(self.approver, "is_approved", None)
        if callable(checker) and not checker(approval_id):
            rejected = getattr(self.approver, "is_rejected", None)
            status = "rejected" if callable(rejected) and rejected(approval_id) else "pending"
            return {"approval_id": None, "approved": False, "status": status}
        self._approval_id = approval_id
        self._approved_steps = self._steps_for(approval_id)
        return {"approval_id": approval_id, "approved": True}

    def execute_approved(self, approval_id: str) -> GuardianReport:
        """Ejecuta solo los pasos aprobados del plan ya propuesto."""
        resumed = self.tool_resume_approval(approval_id)
        report = GuardianReport(
            exposures=list(self._exposures),
            anomalies=list(self._anomalies),
            plan=self._plan,
            approval_id=approval_id if resumed.get("approved") else None,
        )
        if not resumed.get("approved"):
            report.summary = f"sin ejecutar: aprobación {resumed.get('status', 'pending')}"
            return report
        for step in self._plan.steps if self._plan else []:
            if step.action in EFFECT_TOOLS:
                if (step.action, step.target) not in self._approved_steps:
                    report.executed.append(
                        {"action": step.action, "target": step.target, "status": "skipped"}
                    )
                    continue
                result = self.dispatch(
                    step.action,
                    {
                        "agent": step.target,
                        "provider": step.target,
                        "token_id": step.target,
                        "approval_id": approval_id,
                    },
                )
                report.executed.append({"action": step.action, "target": step.target, **result})
            elif step.action == "verify":
                report.executed.append(
                    {"action": "verify", "target": step.target, **self.tool_verify(step.target)}
                )
        report.summary = (
            f"exposures={len(report.exposures)} anomalies={len(report.anomalies)} "
            f"executed={len(report.executed)} approval={approval_id}"
        )
        return report

    # -- herramientas con efecto (exigen approval_id de ask_owner) ----------

    def _require_approval(self, action: str, target: str, approval_id: str) -> str | None:
        if self.actions is None:
            return "sin backend de acciones (H6): nada que ejecutar"
        if not approval_id or approval_id != self._approval_id:
            return "approval_required: pide primero ask_owner y usa su approval_id"
        if (action, target) not in self._approved_steps:
            return f"paso no aprobado en el plan: {action} {target}"
        return None

    def tool_rotate_token(self, agent: str, approval_id: str = "") -> dict[str, Any]:
        error = self._require_approval("rotate_token", agent, approval_id)
        if error:
            return {"status": "blocked", "reason": error}
        assert self.actions is not None
        return self.actions.rotate_token(agent, approval_id)

    def tool_rotate_upstream_key(self, provider: str, approval_id: str = "") -> dict[str, Any]:
        error = self._require_approval("rotate_upstream_key", provider, approval_id)
        if error:
            return {"status": "blocked", "reason": error}
        assert self.actions is not None
        return self.actions.rotate_upstream_key(provider, approval_id)

    def tool_revoke(self, token_id: str, approval_id: str = "") -> dict[str, Any]:
        error = self._require_approval("revoke", token_id, approval_id)
        if error:
            return {"status": "blocked", "reason": error}
        assert self.actions is not None
        return self.actions.revoke(token_id, approval_id)

    def tool_verify(self, target: str) -> dict[str, Any]:
        if self.actions is None:
            return {"status": "unavailable", "target": target}
        return self.actions.verify(target)

    def tool_draft_notice(self, regime: str = "rgpd") -> dict[str, Any]:
        draft = draft_notice(
            summary=(self._plan.summary if self._plan else "incidente detectado por el guardián"),
            exposures=self._exposures,
            anomalies=self._anomalies,
            regime=regime if regime in ("rgpd", "lopdp") else "rgpd",
        )
        return {"title": draft.title, "body": draft.render()}

    # -- despacho y corridas --------------------------------------------------

    def dispatch(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        handlers: dict[str, Any] = {
            "match_exposure": lambda: self.tool_match_exposure(),
            "detect_anomaly": lambda: self.tool_detect_anomaly(),
            "propose_plan": lambda: self.tool_propose_plan(),
            "ask_owner": lambda: self.tool_ask_owner(),
            "resume_approval": lambda: self.tool_resume_approval(str(args.get("approval_id", ""))),
            "rotate_token": lambda: self.tool_rotate_token(
                str(args.get("agent", "")), str(args.get("approval_id", ""))
            ),
            "rotate_upstream_key": lambda: self.tool_rotate_upstream_key(
                str(args.get("provider", "")), str(args.get("approval_id", ""))
            ),
            "verify": lambda: self.tool_verify(str(args.get("target", ""))),
            "revoke": lambda: self.tool_revoke(
                str(args.get("token_id", "")), str(args.get("approval_id", ""))
            ),
            "draft_notice": lambda: self.tool_draft_notice(str(args.get("regime", "rgpd"))),
        }
        handler = handlers.get(name)
        if handler is None:
            return {"status": "error", "reason": f"herramienta desconocida: {name}"}
        return handler()

    def run_once(self) -> GuardianReport:
        """Pipeline determinista: vigila, propone, pide OK y solo entonces actúa."""
        self.tool_match_exposure()
        self.tool_detect_anomaly()
        plan_dict = self.tool_propose_plan()
        report = GuardianReport(
            exposures=list(self._exposures), anomalies=list(self._anomalies), plan=self._plan
        )
        effect_steps = [
            s for s in (self._plan.steps if self._plan else []) if s.action in EFFECT_TOOLS
        ]
        if effect_steps:
            asked = self.tool_ask_owner()
            report.approval_id = asked.get("approval_id")
            if report.approval_id:
                for step in self._plan.steps if self._plan else []:
                    if step.action in EFFECT_TOOLS:
                        if (step.action, step.target) not in self._approved_steps:
                            report.executed.append(
                                {
                                    "action": step.action,
                                    "target": step.target,
                                    "status": "skipped",
                                }
                            )
                            continue
                        result = self.dispatch(
                            step.action,
                            {
                                "agent": step.target,
                                "provider": step.target,
                                "token_id": step.target,
                                "approval_id": report.approval_id,
                            },
                        )
                        report.executed.append(
                            {"action": step.action, "target": step.target, **result}
                        )
                    elif step.action == "verify":
                        report.executed.append(
                            {
                                "action": "verify",
                                "target": step.target,
                                **self.tool_verify(step.target),
                            }
                        )
        if self._plan and any(s.action == "draft_notice" for s in self._plan.steps):
            draft = draft_notice(
                summary=plan_dict["summary"],
                exposures=self._exposures,
                anomalies=self._anomalies,
                regime="rgpd",
            )
            report.notices.append(draft)
        report.summary = (
            f"exposures={len(report.exposures)} anomalies={len(report.anomalies)} "
            f"executed={len(report.executed)} approval={report.approval_id or 'none'}"
        )
        return report

    def run_with_model(self, *, max_steps: int = 8) -> GuardianReport:
        """Loop de tool calling con Spark 1.3; sin créditos cae a run_once."""
        from shield.meta_client import NeedsCredits

        if self.client is None:
            report = self.run_once()
            report.needs_credits = True
            return report
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": f"Eres el agente guardián de {BRAND}. "
                "Vigila, propón un plan, pide aprobación y actúa solo con approval_id.",
            },
            {"role": "user", "content": "Corre un ciclo de vigilancia completo y reporta."},
        ]
        try:
            for _ in range(max_steps):
                result = self.client.chat_completions(
                    model="muse-spark-1.3", messages=messages, tools=TOOL_SCHEMAS
                )
                choices = result.data.get("choices") or []
                message = (choices[0].get("message") or {}) if choices else {}
                calls = message.get("tool_calls") or []
                if not calls:
                    break
                messages.append(
                    {"role": "assistant", "content": message.get("content"), "tool_calls": calls}
                )
                for call in calls:
                    fn = call.get("function") or {}
                    try:
                        tool_args = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        tool_args = {}
                    outcome = self.dispatch(str(fn.get("name", "")), tool_args)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id", ""),
                            "content": json.dumps(outcome, default=str)[:4000],
                        }
                    )
        except NeedsCredits:
            report = self.run_once()
            report.needs_credits = True
            return report
        report = GuardianReport(
            exposures=list(self._exposures),
            anomalies=list(self._anomalies),
            plan=self._plan,
            approval_id=self._approval_id,
        )
        report.summary = (
            f"model-loop exposures={len(report.exposures)} anomalies={len(report.anomalies)} "
            f"approval={report.approval_id or 'none'}"
        )
        return report
