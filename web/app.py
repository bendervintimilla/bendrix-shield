"""Panel web de Shield (H8): FastAPI + HTMX, una página, sin build.

Muestra apps y agentes conectados, el flujo en vivo de decisiones de la
política (``CallLog`` del gateway), incidentes con su exposición, botones
de aprobación (plan B de WhatsApp), la terminal del atacante
(``200 → 401``) y un cronómetro desde el incidente. Con ``DEMO=replay``
(o por defecto en este módulo) todo corre en memoria con un upstream
falso: sin red ni créditos. La tarjeta visual con Muse Image se cortó:
no sumaba frente al riesgo de enseñarlo sin créditos (ver web/README.md).
"""

from __future__ import annotations

import html
import json
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response

from channels.approvals import ApprovalBroker, ChannelApprover
from channels.voice import VoiceApprovalFlow
from channels.whatsapp import WhatsAppChannel
from channels.whatsapp import create_router as whatsapp_router
from shield.actions import Actions
from shield.agent import GuardianAgent, RunbookGuardianActions
from shield.registry import Registry
from shield.schemas import CallLog
from shield.sdk.token_store import InMemoryTokenStore
from web.brand import BRAND, SUBTITLE
from web.live_page import render_live_inactive_page, render_live_page

UPSTREAM_KEY = "upstream-demo-key-0000"

T: dict[str, dict[str, str]] = {
    "en": {
        "replay": "Replay — test tokens, fake upstream, no real keys",
        "restart": "Restart demo",
        "headline_pending": "Someone is using Warehouse's stolen token.",
        "headline_contained": "The thief is locked out.",
        "headline_rejected": "You rejected the plan. The stolen token still works.",
        "headline_not_rotated": "Nothing was rotated. The stolen token still works.",
        "stolen_attempts": "Stolen token attempts",
        "attempts": "attempts",
        "attempt": "attempt",
        "support_contained": "Warehouse's old token is revoked. The attacker now gets 401.",
        "support_attacker_200": "The attacker still gets 200.",
        "in_total": "in total",
        "stopped_in": "Stopped in",
        "real_incident": "~16 h in the real incident",
        "your_decision": "Your decision",
        "approve": "Approve",
        "reject": "Reject",
        "voice_label": "Voice note (transcript)",
        "send": "Send",
        "confirm": "Confirm",
        "cancel": "Cancel",
        "what_happened": "What was decided",
        "executed": "Carried out",
        "nothing_executed": "Nothing carried out yet.",
        "decided_contained": "You approved the plan. The stolen token no longer works.",
        "decided_rejected": "You rejected the plan. Nothing was rotated.",
        "decided_not_rotated": "The plan was approved, but no token was rotated.",
        "decided_done": "The plan was carried out.",
        "warehouse": "Warehouse",
        "warehouse_keeps": "keeps counting",
        "warehouse_working": "is working",
        "warehouse_new_token": "Same agent, new token from the local store",
        "warehouse_current_token": "Same agent, still on its current token",
        "attacker": "Attacker",
        "retry_attacker": "Retry as attacker",
        "stolen": "stolen",
        "untouched": "untouched",
        "agents": "Agents",
        "anomalies": "Anomalies",
        "no_anomalies": "No anomalies.",
        "agent": "Agent",
        "app": "App",
        "status": "Status",
        "models": "Models",
        "token_id": "Token id",
        "decisions": "Policy decisions",
        "no_calls": "No calls yet.",
        "time": "Time",
        "decision": "Decision",
        "country": "Country",
        "models_run": "Where Meta models run",
        "replay_note": (
            "This screen is a replay: the guardian flow runs on our gateway "
            "without calling a model. Live model runs are logged in evals/report.md."
        ),
        "model": "Model",
        "what_it_does": "What it does",
        "where_it_runs": "Where it runs",
        "figures": (
            "Held-out v2: 0/12 sensitive writes silently allowed; 4 blocked, "
            "7 sent to the owner, 1 English read passed silently (we say so). "
            "200 → 401 in <10 s in replay vs ~16 h in the real incident."
        ),
        "active": "Active",
        "revoked": "Revoked",
        "allow": "Allowed",
        "block": "Blocked",
        "ask_owner": "Sent to owner",
    },
    "es": {
        "replay": "Replay — tokens de prueba, upstream falso, sin llaves reales",
        "restart": "Reiniciar demo",
        "headline_pending": "Alguien está usando el token robado de Bodega.",
        "headline_contained": "El ladrón quedó fuera.",
        "headline_rejected": "Rechazaste el plan. El token robado sigue funcionando.",
        "headline_not_rotated": "No se rotó nada. El token robado sigue funcionando.",
        "stolen_attempts": "Intentos con el token robado",
        "attempts": "intentos",
        "attempt": "intento",
        "support_contained": (
            "El token viejo de Bodega quedó revocado. El atacante ahora recibe 401."
        ),
        "support_attacker_200": "El atacante sigue recibiendo 200.",
        "in_total": "en total",
        "stopped_in": "Detenido en",
        "real_incident": "~16 h en el incidente real",
        "your_decision": "Tu decisión",
        "approve": "Aprobar",
        "reject": "Rechazar",
        "voice_label": "Nota de voz (transcripción)",
        "send": "Enviar",
        "confirm": "Confirmar",
        "cancel": "Cancelar",
        "what_happened": "Lo que se decidió",
        "executed": "Ejecutado",
        "nothing_executed": "Nada ejecutado todavía.",
        "decided_contained": "Aprobaste el plan. El token robado ya no funciona.",
        "decided_rejected": "Rechazaste el plan. No se rotó nada.",
        "decided_not_rotated": "El plan se aprobó, pero no se rotó ningún token.",
        "decided_done": "El plan se ejecutó.",
        "warehouse": "Bodega",
        "warehouse_keeps": "sigue contando",
        "warehouse_working": "está trabajando",
        "warehouse_new_token": "El mismo agente, con token nuevo de la tienda local",
        "warehouse_current_token": "El mismo agente, todavía con su token actual",
        "attacker": "Atacante",
        "retry_attacker": "Reintentar como atacante",
        "stolen": "robado",
        "untouched": "sin tocar",
        "agents": "Agentes",
        "anomalies": "Anomalías",
        "no_anomalies": "Sin anomalías.",
        "agent": "Agente",
        "app": "App",
        "status": "Estado",
        "models": "Modelos",
        "token_id": "Id del token",
        "decisions": "Decisiones de la política",
        "no_calls": "Todavía no hay llamadas.",
        "time": "Hora",
        "decision": "Decisión",
        "country": "País",
        "models_run": "Dónde corren los modelos de Meta",
        "replay_note": (
            "Esta pantalla es un replay: el flujo del guardián corre en nuestro "
            "gateway sin llamar a un modelo. Las corridas en vivo están en evals/report.md."
        ),
        "model": "Modelo",
        "what_it_does": "Qué hace",
        "where_it_runs": "Dónde corre",
        "figures": (
            "Held-out v2: 0/12 escrituras sensibles permitidas en silencio; 4 bloqueadas, "
            "7 al dueño, 1 lectura en inglés pasó en silencio (se dice). "
            "200 → 401 en <10 s en replay frente a ~16 h del incidente real."
        ),
        "active": "Activo",
        "revoked": "Revocado",
        "allow": "Permitido",
        "block": "Bloqueado",
        "ask_owner": "Al dueño",
    },
}


def _t(lang: str, key: str) -> str:
    return T.get(lang, T["en"]).get(key, T["en"].get(key, key))


def _agent_display(name: Any, lang: str) -> str:
    raw = str(name)
    if lang == "es":
        return {"bodega": "Bodega", "compras": "Compras"}.get(raw, raw)
    return {"bodega": "Warehouse (bodega)", "compras": "Purchasing (compras)"}.get(raw, raw)


def _notice_name(name: Any) -> str:
    raw = str(name)
    return {"stripe": "Stripe"}.get(raw.lower(), raw)


def _anomaly_text(anomaly: dict[str, Any], lang: str) -> str:
    kind = str(anomaly.get("kind", ""))
    agent = _agent_display(anomaly.get("agent", ""), lang)
    evidence: dict[str, str] = {}
    for item in anomaly.get("evidence") or []:
        if ":" in str(item):
            k, v = str(item).split(":", 1)
            evidence[k] = v
    if kind == "new_country":
        country = evidence.get("country", "")
        if lang == "es":
            return (
                f"País nuevo: {agent} está llamando desde {country}, "
                "un país que no usa normalmente."
            )
        return (
            f"New country: {agent} is calling from {country}, a country it does not normally use."
        )
    if kind == "new_model":
        model = evidence.get("model", "")
        if lang == "es":
            return f"Modelo no usado: {agent} está usando {model}, fuera de su línea base."
        return f"Unused model: {agent} is using {model}, outside its baseline."
    if kind == "cost_spike":
        if lang == "es":
            return (
                f"Pico de costo: el costo por llamada de {agent} está muy sobre su mediana usual."
            )
        return f"Cost spike: cost per call for {agent} is well above its usual median."
    return str(anomaly.get("detail", kind))


def _fmt_clock(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


def _status_blocks(statuses: list[int], *, agent: bool = False) -> str:
    if not statuses:
        return "<span class='code-block code-none'>—</span>"
    parts = []
    for s in statuses:
        code = int(s)
        cls = "code-agent-200" if agent and code == 200 else f"code-{code}"
        parts.append(f"<span class='code-block {cls}'>{code}</span>")
    return "".join(parts)


_ADVISORY_PATH = (
    Path(__file__).resolve().parents[1]
    / "evals"
    / "advisories"
    / "railway-2026-10-21-env-exposure.json"
)

_MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_MONTHS_ES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def _advisory_line(lang: str = "en") -> str:
    try:
        data = json.loads(_ADVISORY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    title = str(data.get("title", "")).strip()
    if not title:
        return ""
    host = urlparse(str(data.get("source_url", ""))).netloc or "blog.railway.com"
    date_text = ""
    try:
        published = datetime.fromisoformat(str(data.get("published_at", "")).replace("Z", "+00:00"))
        months = _MONTHS_ES if lang == "es" else _MONTHS_EN
        date_text = f", {published.day} {months[published.month - 1]} {published.year}"
    except ValueError:
        date_text = ""
    if lang == "es":
        return (
            f"Aviso en archivo: {title}{date_text} · {host} · "
            "sin coincidencia con un activo en este replay; "
            "la alerta viene de la señal de país nuevo."
        )
    # El título del archivo está en español; en inglés se traduce el de Railway.
    if str(data.get("id", "")).startswith("railway-2026-10-21"):
        title = "Railway: anomalous activity on environment variables"
    return (
        f"Advisory on file: {title}{date_text} · {host} · "
        "not matched to an asset in this replay; "
        "the alert comes from the new-country signal."
    )


def _action_plain(action: Any, lang: str) -> str:
    names = {
        "rotate_token": ("Rotate the token", "Rotar el token"),
        "verify": ("Check it still works", "Comprobar que sigue funcionando"),
        "rotate_upstream_key": (
            "Rotate the upstream key",
            "Rotar la clave del proveedor",
        ),
        "revoke": ("Revoke the token", "Revocar el token"),
        "draft_notice": ("Draft a notice", "Preparar un borrador de aviso"),
    }
    pair = names.get(str(action))
    if pair is None:
        return str(action)
    return pair[1] if lang == "es" else pair[0]


def _status_plain(status: Any, lang: str) -> str:
    raw = str(status)
    if lang != "es":
        return "skipped" if raw == "skipped" else raw
    return {
        "applied": "aplicado",
        "ok": "bien",
        "skipped": "omitido",
        "blocked": "bloqueado",
        "revoked": "revocado",
        "unavailable": "no disponible",
        "error": "error",
        "approved": "aprobado",
        "rejected": "rechazado",
    }.get(raw, raw)


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _trim_statuses(statuses: list[int], limit: int = 12) -> list[int]:
    """Recorta a ``limit`` quitando un elemento interno de la racha más larga.

    Así el primer código y cualquier transición (p. ej. 200→401) sobreviven:
    al borrar dentro de una racha queda al menos un ejemplar de ese valor.
    """
    result = list(statuses)
    if limit <= 0:
        return []
    while len(result) > limit:
        best_start = 0
        best_len = 1
        run_start = 0
        for i in range(1, len(result)):
            if result[i] != result[i - 1]:
                run_start = i
            run_len = i - run_start + 1
            if run_len > best_len:
                best_start = run_start
                best_len = run_len
        if best_len >= 2:
            del result[best_start + best_len // 2]
        elif len(result) > 1:
            del result[1]
        else:  # pragma: no cover - limit >= 1 y len > limit lo impide
            del result[0]
    return result


class _ProbeAuthError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class _GatewayProbeClient:
    """Cliente chico estilo OpenAI para sondear el gateway por HTTP real."""

    def __init__(self, gateway: Any, api_key: str) -> None:
        self._gateway = gateway
        self.api_key = api_key

    def ping(self) -> int:
        resp = self._gateway.post(
            "/v1/chat/completions",
            json={
                "model": "muse-spark-1.3",
                "messages": [{"role": "user", "content": "cuenta"}],
            },
            headers={
                "Authorization": f"Bearer {self.api_key or ''}",
                "X-Demo-Country": "EC",
            },
        )
        status = int(resp.status_code)
        if status == 401:
            raise _ProbeAuthError(401)
        if status >= 400:
            raise _ProbeAuthError(status)
        return status


class _CountryGateway:
    """Adaptador con ``.post`` que inyecta ``X-Demo-Country`` al gateway."""

    def __init__(self, gateway: Any, country: str) -> None:
        self._gateway = gateway
        self._country = country

    def post(self, url: str, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", None) or {})
        headers["X-Demo-Country"] = self._country
        return self._gateway.post(url, headers=headers, **kwargs)


def _upstream_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-demo",
            "model": "muse-spark-1.3",
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 4},
        },
    )


def _logs(agent: str, country: str, model: str, cost: float, n: int = 3) -> list[CallLog]:
    return [
        CallLog(
            ts=datetime(2026, 10, 28, 8 + i, tzinfo=UTC),
            agent=agent,
            model=model,
            cost_usd=cost,
            src_country=country,
        )
        for i in range(n)
    ]


@dataclass
class DemoState:
    registry: Registry
    broker: ApprovalBroker
    guardian: GuardianAgent
    gateway: Any
    token_store: InMemoryTokenStore
    attacker_raw: str = field(repr=False, default="")
    attacker_statuses: list[int] = field(default_factory=list)
    attempts_total: int = 0
    agent_statuses: dict[str, list[int]] = field(default_factory=dict)
    executed: list[dict[str, Any]] = field(default_factory=list)
    started_monotonic: float = field(default_factory=time.monotonic)
    incident_at: str = ""
    clock_started_at: float | None = None
    contained_in_s: float | None = None
    voice_flow: Any = field(default=None, repr=False)
    voice_notice: dict[str, Any] = field(default_factory=dict)
    agent_refreshes: dict[str, int] = field(default_factory=dict)
    _probe_clients: dict[str, Any] = field(default_factory=dict, repr=False)
    version: int = 0
    autotick_ticks: int = 0
    _executed_approval_ids: set[str] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        if self.voice_flow is None:
            self.voice_flow = VoiceApprovalFlow(self.broker)

    # -- utilidades internas ------------------------------------------------

    def _touch(self) -> None:
        self.version += 1

    def start_clock(self) -> None:
        if self.clock_started_at is None:
            self.clock_started_at = time.monotonic()
            self._touch()

    def elapsed_s(self) -> float:
        if self.clock_started_at is None:
            return 0.0
        if self.contained_in_s is not None:
            return float(self.contained_in_s)
        return round(time.monotonic() - self.clock_started_at, 1)

    @property
    def clock_running(self) -> bool:
        return self.clock_started_at is not None and self.contained_in_s is None

    def _has_applied_bodega_rotation(self) -> bool:
        return any(
            e.get("action") == "rotate_token"
            and e.get("target") == "bodega"
            and e.get("status") == "applied"
            for e in self.executed
        )

    @property
    def phase(self) -> str:
        if self.contained_in_s is not None:
            return "contained"
        if self._has_applied_bodega_rotation() and self.attacker_statuses:
            if self.attacker_statuses[-1] == 401:
                return "contained"
        awaiting = getattr(self.voice_flow, "_awaiting", {}) if self.voice_flow else {}
        if awaiting:
            for approval_id in awaiting:
                req = self.broker.get(approval_id)
                if req is not None and req.status == "pending":
                    return "awaiting_confirmation"
        if self.voice_notice.get("status") == "confirmation_required":
            approval_id = self.voice_notice.get("approval_id")
            req = self.broker.get(str(approval_id)) if approval_id else None
            if req is not None and req.status == "pending":
                return "awaiting_confirmation"
        requests = list(self.broker.requests.values())
        if any(r.status == "approved" for r in requests):
            return "not_rotated"
        if any(r.status == "rejected" for r in requests):
            return "rejected"
        return "pending"

    def _agent_names(self) -> list[str]:
        names: list[str] = []
        for token in self.registry.list_tokens():
            if token.status.value == "active" and token.agent not in names:
                names.append(token.agent)
        return names

    # -- sondas ---------------------------------------------------------------

    def probe_attacker(self) -> int:
        from sandbox.attacker import attempt_statuses

        adapter = _CountryGateway(self.gateway, "BR")
        statuses = attempt_statuses(adapter, self.attacker_raw, attempts=1)
        self.attempts_total += len(statuses)
        self.attacker_statuses = _trim_statuses([*self.attacker_statuses, *statuses])
        status = statuses[0] if statuses else 0
        if (
            status == 401
            and self.contained_in_s is None
            and self.clock_started_at is not None
            and self._has_applied_bodega_rotation()
        ):
            self.contained_in_s = round(time.monotonic() - self.clock_started_at, 1)
            # Tras contener quedan 3 ticks automáticos más y se detiene.
            self.autotick_ticks = 0
        self._touch()
        return status

    def probe_agents(self) -> None:
        for name in self._agent_names():
            self.probe_agent(name)

    @property
    def autotick_limit(self) -> int:
        return 3 if self.phase == "contained" else 12

    @property
    def autotick_active(self) -> bool:
        return self.autotick_ticks < self.autotick_limit

    def _probe_client(self, name: str) -> Any:
        from shield.sdk.refresh import ShieldClient

        wrapped = self._probe_clients.get(name)
        if wrapped is None:
            raw = self.token_store.get_token(name) or ""
            small = _GatewayProbeClient(self.gateway, raw)
            wrapped = ShieldClient(small, self.token_store, name)
            self._probe_clients[name] = wrapped
        return wrapped

    def probe_agent(self, name: str) -> int:
        wrapped = self._probe_client(name)
        raw_client = wrapped.raw
        before = getattr(raw_client, "api_key", None)
        try:
            status = int(wrapped.ping())
        except Exception as exc:
            status = int(getattr(exc, "status_code", 0) or 0)
        after = getattr(raw_client, "api_key", None)
        if before is not None and after is not None and after != before:
            self.agent_refreshes[name] = int(self.agent_refreshes.get(name, 0)) + 1
        current = self.agent_statuses.get(name, [])
        self.agent_statuses[name] = _trim_statuses([*current, status])
        self._touch()
        return status

    # -- ejecución ------------------------------------------------------------

    def _execute_approved_once(self, approval_id: str) -> Any:
        if approval_id in self._executed_approval_ids:
            return None
        self.start_clock()
        report = self.guardian.execute_approved(approval_id)
        if not report.approval_id:
            return report
        self._executed_approval_ids.add(approval_id)
        self.executed = report.executed
        self._touch()
        return report

    def approve_and_execute(self, approval_id: str) -> dict[str, Any]:
        req = self.broker.get(approval_id)
        if req is None:
            raise KeyError(f"aprobación no encontrada: {approval_id}")
        if approval_id in self._executed_approval_ids:
            return {
                "approval_id": approval_id,
                "executed": self.executed,
                "summary": "ya ejecutado",
            }
        if req.status == "pending":
            self.start_clock()
            self.broker.approve(approval_id)
        elif req.status != "approved":
            raise ValueError(f"aprobación {approval_id} no está pendiente: {req.status}")
        report = self._execute_approved_once(approval_id)
        executed = report.executed if report is not None else self.executed
        summary = report.summary if report is not None else ""
        self.autotick_ticks = 0
        self.probe_attacker()
        self.probe_agents()
        return {"approval_id": approval_id, "executed": executed, "summary": summary}

    def reject(self, approval_id: str) -> dict[str, Any]:
        req = self.broker.get(approval_id)
        if req is None:
            raise KeyError(f"aprobación no encontrada: {approval_id}")
        if req.status == "rejected":
            return {"approval_id": approval_id, "status": "rejected"}
        if req.status != "pending":
            raise ValueError(f"aprobación {approval_id} no está pendiente: {req.status}")
        self.broker.reject(approval_id)
        self._touch()
        self.autotick_ticks = 0
        self.probe_attacker()
        self.probe_agents()
        return {"approval_id": approval_id, "status": "rejected"}

    # -- voz --------------------------------------------------------------------

    def _set_voice_notice(self, notice: dict[str, Any]) -> dict[str, Any]:
        self.voice_notice = {
            key: (list(value) if isinstance(value, list) else value)
            for key, value in notice.items()
        }
        self._touch()
        return self.voice_notice

    def _notice_from_outcome(
        self, approval_id: str, transcript: str, outcome: dict[str, Any]
    ) -> dict[str, Any]:
        intent = outcome.get("intent") or {}
        notice: dict[str, Any] = {
            "status": str(outcome.get("status", "unknown_command")),
            "approval_id": approval_id,
            "transcript": transcript or str(intent.get("transcript", "")),
        }
        if intent.get("is_partial") or "will_run" in outcome:
            notice["will_run"] = list(outcome.get("will_run") or [])
            notice["excluded"] = list(
                outcome.get("excluded") or intent.get("exclude_targets") or []
            )
            notice["unmatched"] = list(outcome.get("unmatched") or [])
        return notice

    def handle_voice(
        self, approval_id: str, transcript: str, *, confirmed: bool = False
    ) -> dict[str, Any]:
        req = self.broker.get(approval_id)
        if req is None:
            return self._set_voice_notice(
                {"status": "not_pending", "approval_id": approval_id, "transcript": transcript}
            )
        if req.status != "pending" and not (
            confirmed and self.voice_flow.awaiting_intent(approval_id) is not None
        ):
            return self._set_voice_notice(
                {"status": "not_pending", "approval_id": approval_id, "transcript": transcript}
            )
        outcome = self.voice_flow.handle_transcript(approval_id, transcript, confirmed=confirmed)
        notice = self._notice_from_outcome(approval_id, transcript, outcome)
        self._set_voice_notice(notice)
        if notice["status"] == "approved":
            self._execute_approved_once(approval_id)
            self.autotick_ticks = 0
            self.probe_attacker()
            self.probe_agents()
        elif notice["status"] == "rejected":
            self.autotick_ticks = 0
            self.probe_attacker()
            self.probe_agents()
        return self.voice_notice

    def confirm_voice(self, approval_id: str) -> dict[str, Any]:
        req = self.broker.get(approval_id)
        if req is None:
            return self._set_voice_notice(
                {"status": "not_pending", "approval_id": approval_id, "transcript": ""}
            )
        awaiting = self.voice_flow.awaiting_intent(approval_id)
        if awaiting is None:
            return self._set_voice_notice(
                {
                    "status": "nothing_to_confirm",
                    "approval_id": approval_id,
                    "transcript": str(self.voice_notice.get("transcript", "")),
                }
            )
        if req.status != "pending":
            return self._set_voice_notice(
                {
                    "status": "not_pending",
                    "approval_id": approval_id,
                    "transcript": awaiting.transcript,
                }
            )
        outcome = self.voice_flow.confirm(approval_id)
        notice = self._notice_from_outcome(approval_id, awaiting.transcript, outcome)
        self._set_voice_notice(notice)
        if notice["status"] == "approved":
            self._execute_approved_once(approval_id)
            self.autotick_ticks = 0
            self.probe_attacker()
            self.probe_agents()
        elif notice["status"] == "rejected":
            self.autotick_ticks = 0
            self.probe_attacker()
            self.probe_agents()
        return self.voice_notice

    def cancel_voice(self, approval_id: str) -> dict[str, Any]:
        req = self.broker.get(approval_id)
        if req is None:
            return self._set_voice_notice(
                {"status": "not_pending", "approval_id": approval_id, "transcript": ""}
            )
        awaiting = self.voice_flow.awaiting_intent(approval_id)
        outcome = self.voice_flow.cancel(approval_id)
        transcript = awaiting.transcript if awaiting is not None else ""
        notice: dict[str, Any] = {
            "status": str(outcome.get("status", "nothing_to_confirm")),
            "approval_id": approval_id,
            "transcript": transcript,
        }
        if awaiting is not None and awaiting.is_partial:
            from channels.voice import plan_preview

            preview = plan_preview(req.plan, awaiting)
            notice.update(preview)
        return self._set_voice_notice(notice)

    # -- tick -------------------------------------------------------------------

    def tick(self) -> dict[str, Any]:
        if not self.autotick_active:
            return self.public()
        self.autotick_ticks += 1
        for req in list(self.broker.requests.values()):
            if req.status == "approved" and req.approval_id not in self._executed_approval_ids:
                self._execute_approved_once(req.approval_id)
                break
        self.probe_attacker()
        self.probe_agents()
        return self.public()

    def public(self) -> dict[str, Any]:
        from sandbox.attacker import format_timeline

        tokens = [t.model_dump(mode="json") for t in self.registry.list_tokens()]
        calls = [c.model_dump(mode="json") for c in self.registry.list_calls()]
        guardian = self.guardian
        incidents = {
            "exposures": [e.model_dump(mode="json") for e in guardian._exposures],
            "anomalies": [vars(a) for a in guardian._anomalies],
            "plan": guardian._plan.to_dict() if guardian._plan else None,
        }
        voice_notice = {
            key: (list(value) if isinstance(value, list) else value)
            for key, value in self.voice_notice.items()
        }
        return {
            "demo": os.environ.get("DEMO", "replay"),
            "agents": tokens,
            "apps": sorted({t["app"] for t in tokens}),
            "calls": calls,
            "incidents": incidents,
            "pending": [r.public() for r in self.broker.list_pending()],
            "requests": [r.public() for r in self.broker.requests.values()],
            "executed": self.executed,
            "attacker_timeline": format_timeline(self.attacker_statuses),
            "attacker_statuses": list(self.attacker_statuses),
            "attempts_total": self.attempts_total,
            "agent_statuses": {k: list(v) for k, v in self.agent_statuses.items()},
            "agent_refreshes": dict(self.agent_refreshes),
            "phase": self.phase,
            "clock_running": self.clock_running,
            "contained_in_s": self.contained_in_s,
            "voice_notice": voice_notice,
            "autotick": 1 if self.autotick_active else 0,
            "autotick_ticks": self.autotick_ticks,
            "version": self.version,
            "elapsed_s": self.elapsed_s(),
            "incident_at": self.incident_at,
        }


def build_replay_state() -> DemoState:
    from fastapi.testclient import TestClient

    from shield.gateway.app import UPSTREAM_KEY_NAME, create_app
    from shield.vault import MemoryVault

    registry = Registry(":memory:")
    broker = ApprovalBroker()
    gateway_app = create_app(
        registry=registry,
        vault=MemoryVault({UPSTREAM_KEY_NAME: UPSTREAM_KEY}),
        upstream_transport=httpx.MockTransport(_upstream_ok),
        sandbox=True,
    )
    gateway = TestClient(gateway_app)
    store = InMemoryTokenStore()
    bodega, bodega_raw = registry.create_token(
        "bodega", "crew", models=["sam-3.1", "muse-spark-1.3"]
    )
    compras, compras_raw = registry.create_token("compras", "crew", models=["muse-spark-1.3"])
    store.set_token("bodega", bodega_raw, bodega.token_id)
    store.set_token("compras", compras_raw, compras.token_id)
    actions = Actions(registry=registry, token_store=store, approvals=broker.registry, sandbox=True)
    approver = ChannelApprover(broker)
    guardian = GuardianAgent(
        logs=_logs("bodega", "BR", "muse-spark-1.3", 18.0),
        baseline=_logs("bodega", "EC", "sam-3.1", 1.0),
        actions=RunbookGuardianActions(actions, grace_s=0.0),
        approver=approver,
    )
    state = DemoState(
        registry=registry,
        broker=broker,
        guardian=guardian,
        gateway=gateway,
        token_store=store,
        attacker_raw=bodega_raw,
        incident_at=datetime.now(UTC).isoformat(),
    )
    # Flujo de la demo: anomalía → guardián → ask_owner queda pendiente.
    gateway.post(
        "/v1/chat/completions",
        json={"model": "muse-spark-1.3", "messages": [{"role": "user", "content": "cuenta"}]},
        headers={"Authorization": f"Bearer {bodega_raw}", "X-Demo-Country": "BR"},
    )
    guardian.tool_match_exposure()
    guardian.tool_detect_anomaly()
    guardian.tool_propose_plan()
    guardian.tool_ask_owner()
    state.probe_attacker()
    for agent_name in state._agent_names():
        state.probe_agent(agent_name)
    return state


def _agents_html(state: DemoState, lang: str = "en") -> str:
    def status_label(value: str) -> str:
        return _t(lang, value) if value in ("active", "revoked") else value

    rows = "".join(
        f"<tr><td>{_esc(_agent_display(t.agent, lang))}</td><td>{_esc(t.app)}</td>"
        f"<td><span class='status status-{_esc(t.status.value)}'>"
        f"{_esc(status_label(t.status.value))}</span></td>"
        f"<td class='col-models'>{_esc(', '.join(t.models))}</td>"
        f"<td class='col-token'><code>{_esc(t.token_id)}</code></td></tr>"
        for t in state.registry.list_tokens()
    )
    return (
        f"<div class='tablewrap'><table class='agents-table'><thead><tr>"
        f"<th>{_t(lang, 'agent')}</th>"
        f"<th>{_t(lang, 'app')}</th><th>{_t(lang, 'status')}</th>"
        f"<th class='col-models'>{_t(lang, 'models')}</th>"
        f"<th class='col-token'>{_t(lang, 'token_id')}</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )


def _decisions_html(state: DemoState, lang: str = "en") -> str:
    calls = state.registry.list_calls()
    total = len(calls)
    recent = list(reversed(calls[-8:]))
    items = "".join(
        f"<li>{_esc(c.ts.strftime('%H:%M:%S'))} · {_esc(_agent_display(c.agent, lang))} · "
        f"{_esc(c.model)} · {_esc(_t(lang, c.decision.value))} · "
        f"{_esc(c.src_country or '—')}</li>"
        for c in recent
    )
    empty = f"<li>{_t(lang, 'no_calls')}</li>"
    return (
        f"<p class='decisions-total'>{total} {_t(lang, 'in_total')}</p>"
        f"<ul class='feed'>{items or empty}</ul>"
    )


def _plan_step_plain(step: dict[str, Any], state: DemoState, lang: str) -> str:
    action = str(step.get("action", ""))
    target = str(step.get("target", ""))
    who = _agent_display(target, lang) if target in ("bodega", "compras") else target
    if target == "incidente":
        who = "incident" if lang == "en" else "incidente"
    anomalies = [vars(a) for a in state.guardian._anomalies]
    anomaly_line = _anomaly_text(anomalies[0], lang) if anomalies else ""
    if action == "draft_notice":
        what = _action_plain(action, lang)
        why = (
            "A draft for a person to review; nothing is sent."
            if lang == "en"
            else "Un borrador para que lo revise una persona; no se envía nada."
        )
        return f"<li><strong>{_esc(what)}.</strong> {_esc(why)}</li>"
    if action == "rotate_token":
        what = _action_plain(action, lang)
        why = anomaly_line or str(step.get("reason", ""))
    elif action == "verify":
        what = _action_plain(action, lang)
        why = (
            "Check after the rotation that the agent still gets in."
            if lang == "en"
            else "Comprobar tras la rotación que el agente sigue entrando."
        )
    else:
        what, why = _action_plain(action, lang), str(step.get("reason", ""))
    return f"<li><strong>{_esc(what)}</strong> — {_esc(who)}. {_esc(why)}</li>"


def _decision_html(state: DemoState, lang: str = "en") -> str:
    data = state.public()
    pending = data["pending"]
    if pending:
        req = pending[0]
        aid = _esc(req["approval_id"])
        steps = "".join(_plan_step_plain(s, state, lang) for s in (req["plan"].get("steps") or []))
        return (
            f"<div class='decision-grid'><div><ol class='plan'>{steps}</ol>"
            f"<div class='actions'>"
            f"<form method='post' action='/panel/approve/{aid}'>"
            f"<button class='btn primary' type='submit'>{_t(lang, 'approve')}</button></form>"
            f"<form method='post' action='/panel/reject/{aid}'>"
            f"<button class='btn secondary' type='submit'>{_t(lang, 'reject')}</button></form>"
            f"</div></div>"
            f"<div class='voice-box'>"
            f"<form method='post' action='/panel/voice'>"
            f"<input type='hidden' name='approval_id' value='{aid}'>"
            f"<label for='voice-transcript'>{_t(lang, 'voice_label')}</label>"
            f"<input id='voice-transcript' name='transcript' value='sí, rota todo'>"
            f"<button class='btn secondary' type='submit'>{_t(lang, 'send')}</button></form>"
            f"{_voice_notice_html(state, lang)}</div></div>"
        )
    phase = data["phase"]
    key = {
        "contained": "decided_contained",
        "rejected": "decided_rejected",
        "not_rotated": "decided_not_rotated",
    }.get(phase, "decided_done")
    executed = "".join(
        f"<li>{_esc(_action_plain(e.get('action'), lang))} — "
        f"{_esc(_agent_display(e.get('target', ''), lang))}: "
        f"<strong>{_esc(_status_plain(e.get('status'), lang))}</strong></li>"
        for e in data["executed"]
    )
    return (
        f"<p>{_esc(_t(lang, key))}</p>"
        f"<h3>{_t(lang, 'executed')}</h3>"
        f"<ul>{executed or f'<li>{_t(lang, "nothing_executed")}</li>'}</ul>"
        f"<form method='post' action='/panel/reset'>"
        f"<button class='btn primary' type='submit'>{_t(lang, 'restart')}</button></form>"
    )


def _incidents_html(state: DemoState, lang: str = "en") -> str:
    return _decision_html(state, lang)


def _attacker_html(state: DemoState, lang: str = "en") -> str:
    from sandbox.attacker import format_timeline

    timeline = format_timeline(state.attacker_statuses) or "—"
    timeline_html = _esc(timeline).replace("401", "<span class='term-401'>401</span>")
    stolen = _t(lang, "stolen")
    return (
        f"<div class='terminal'><p><code>$ attacker.py --token shd_bodega_… "
        f"({_esc(stolen)})</code></p>"
        f"<p><code>{timeline_html}</code></p></div>"
        f"<form method='post' action='/panel/attacker/probe'>"
        f"<button class='btn secondary' type='submit'>{_t(lang, 'retry_attacker')}</button></form>"
    )


def _voice_notice_html(state: DemoState, lang: str = "en") -> str:
    notice = state.voice_notice
    if not notice:
        return ""
    status = str(notice.get("status", ""))
    transcript = _esc(notice.get("transcript", ""))
    es = lang == "es"
    if status == "confirmation_required":
        will = ", ".join(_notice_name(x) for x in notice.get("will_run") or [])
        will_text = will or ("nada" if es else "nothing")
        left = ", ".join(_notice_name(x) for x in notice.get("excluded") or [])
        left_text = left or ("nada" if es else "nothing")
        unmatched = [_notice_name(x) for x in notice.get("unmatched") or []]
        extra = ""
        if unmatched:
            names = _esc(", ".join(unmatched))
            extra = f" {names} no está en este plan." if es else f" {names} is not in this plan."
        msg = (
            f'Dijiste: "{transcript}". Esto rotará: {_esc(will_text)}. '
            f"Queda fuera: {_esc(left_text)}.{extra}"
            if es
            else f'You said: "{transcript}". This will rotate: {_esc(will_text)}. '
            f"Left out: {_esc(left_text)}.{extra}"
        )
        aid = _esc(notice.get("approval_id", ""))
        buttons = (
            f"<div class='actions'>"
            f"<form method='post' action='/panel/voice/confirm'>"
            f"<input type='hidden' name='approval_id' value='{aid}'>"
            f"<button class='btn primary' type='submit'>{_t(lang, 'confirm')}</button></form>"
            f"<form method='post' action='/panel/voice/cancel'>"
            f"<input type='hidden' name='approval_id' value='{aid}'>"
            f"<button class='btn secondary' type='submit'>{_t(lang, 'cancel')}</button></form>"
            f"</div>"
        )
        return f"<div class='voice-notice' aria-live='polite'><p>{msg}</p>{buttons}</div>"
    messages = {
        "unknown_command": (
            f'No pillé una decisión en "{transcript}". Nada cambió. '
            'Prueba "sí, rota todo" o "rechaza".'
            if es
            else f'Didn\'t catch a decision in "{transcript}". Nothing changed. '
            'Try "yes, rotate it" or "reject".'
        ),
        "not_pending": (
            f'Esa aprobación ya no está pendiente: "{transcript}". Nada cambió.'
            if es
            else f'That approval is no longer pending: "{transcript}". Nothing changed.'
        ),
        "nothing_to_confirm": (
            "No hay nada que confirmar todavía. Nada cambió."
            if es
            else "Nothing to confirm yet. Nothing changed."
        ),
        "cancelled": (
            "Cancelado. Nada cambió y el plan sigue esperando tu decisión."
            if es
            else "Cancelled. Nothing changed and the plan is still waiting for your decision."
        ),
        "approved": ("Aprobado y ejecutado." if es else "Approved and carried out."),
        "rejected": ("Rechazado. No se rotó nada." if es else "Rejected. Nothing was rotated."),
    }
    msg = messages.get(status, f"{_esc(status)}: {transcript}")
    return f"<div class='voice-notice' aria-live='polite'><p>{msg}</p></div>"


def _models_html(lang: str) -> str:
    rows_data = [
        (
            "Muse Spark 1.3",
            "Guardian and crew reasoning, tool calling, invoice vision, "
            "and the ambiguous policy calls."
            if lang == "en"
            else "Razonamiento del guardián y la cuadrilla, llamadas a "
            "herramientas, visión de facturas y casos ambiguos de política.",
            "Live runs logged in evals/report.md; not called on this screen."
            if lang == "en"
            else "Corridas en vivo en evals/report.md; aquí no se lo llama.",
        ),
        (
            "Voice Transcribe",
            "Turns the owner's voice notes into text for approvals and warehouse dictation."
            if lang == "en"
            else "Pasa las notas de voz del dueño a texto para aprobaciones y dictado de bodega.",
            "Live run logged in evals/report.md; this screen uses a typed transcript."
            if lang == "en"
            else "Corrida en vivo en evals/report.md; aquí se usa texto escrito.",
        ),
        (
            "SAM 3.1",
            "Counts warehouse stock from images and video track ids."
            if lang == "en"
            else "Cuenta stock de bodega desde imágenes e ids de video.",
            "Live run logged in evals/report.md (synthetic images); not called here."
            if lang == "en"
            else "Corrida en vivo en evals/report.md (imágenes sintéticas); aquí no se lo llama.",
        ),
        (
            "Muse Wonder",
            "Hard triage only: ambiguous exposures and the difficult cases."
            if lang == "en"
            else "Solo triaje difícil: exposiciones ambiguas y casos complicados.",
            "Live smoke logged in evals/report.md; not called on this screen."
            if lang == "en"
            else "Humo en vivo en evals/report.md; aquí no se lo llama.",
        ),
        (
            "Muse Spark Open",
            "Output gate classifier (open weights)."
            if lang == "en"
            else "Clasificador de salida del gate (pesos abiertos).",
            "Live run pending (no key yet)."
            if lang == "en"
            else "Corrida en vivo pendiente (todavía sin llave).",
        ),
    ]
    rows = "".join(
        f"<tr><td><code>{_esc(m)}</code></td><td>{_esc(d)}</td><td>{_esc(w)}</td></tr>"
        for m, d, w in rows_data
    )
    live_link = (
        f"<p><a href=\"/live\">{_esc(_t(lang, 'models_run'))} — /live</a></p>"
        if os.environ.get("DEMO", "replay") == "live"
        else ""
    )
    return (
        f"{live_link}"
        f"<p>{_esc(_t(lang, 'replay_note'))}</p>"
        f"<div class='tablewrap'><table><thead><tr><th>{_t(lang, 'model')}</th>"
        f"<th>{_t(lang, 'what_it_does')}</th><th>{_t(lang, 'where_it_runs')}</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
        f"<p class='figures'>{_esc(_t(lang, 'figures'))}</p>"
    )


def _app_html(state: DemoState, lang: str = "en") -> str:
    data = state.public()
    phase = data["phase"]
    headline_key = {
        "pending": "headline_pending",
        "awaiting_confirmation": "headline_pending",
        "contained": "headline_contained",
        "rejected": "headline_rejected",
        "not_rotated": "headline_not_rotated",
    }.get(phase, "headline_pending")
    anomalies = data["incidents"]["anomalies"]
    chosen = next(
        (a for a in anomalies if a.get("kind") == "new_country"),
        anomalies[0] if anomalies else None,
    )
    if phase == "contained":
        support = _t(lang, "support_contained")
    elif phase in ("rejected", "not_rotated"):
        support = _t(lang, "support_attacker_200")
    else:
        support = _anomaly_text(chosen, lang) if chosen else _t(lang, "no_calls")
    elapsed = state.elapsed_s()
    clock_value = _fmt_clock(elapsed)
    if phase == "contained":
        clock_html = (
            f"<p class='clock-label'>{_esc(_t(lang, 'stopped_in'))}</p>"
            f"<p id='clock' data-elapsed='{_esc(elapsed)}' "
            f"data-running='0'>{_esc(clock_value)}</p>"
        )
    else:
        clock_html = (
            f"<p id='clock' data-elapsed='{_esc(elapsed)}' "
            f"data-running='{'1' if state.clock_running else '0'}'>"
            f"{_esc(clock_value)}</p>"
        )
    autotick = "1" if data["autotick"] else "0"
    bodega_statuses = data["agent_statuses"].get("bodega", [])
    compras_statuses = data["agent_statuses"].get("compras", [])
    compras_last = compras_statuses[-1] if compras_statuses else "—"
    compras_block = (
        f"<span class='code-block code-agent-200 purchasing-code'>{_esc(compras_last)}</span>"
        if compras_statuses
        else "—"
    )
    rotated = state._has_applied_bodega_rotation()
    warehouse_note = (
        _t(lang, "warehouse_new_token") if rotated else _t(lang, "warehouse_current_token")
    )
    if int(state.agent_refreshes.get("bodega", 0)) > 0:
        warehouse_note = f"{warehouse_note} — refreshed itself once via the SDK"
    warehouse_sub = (
        _t(lang, "warehouse_keeps") if phase == "contained" else _t(lang, "warehouse_working")
    )
    en_current = " aria-current='true'" if lang == "en" else ""
    es_current = " aria-current='true'" if lang == "es" else ""
    attempts_word = _t(lang, "attempt") if data["attempts_total"] == 1 else _t(lang, "attempts")
    attempts_label = f"{_t(lang, 'stolen_attempts')} · {data['attempts_total']} {attempts_word}"
    advisory = _advisory_line(lang)
    advisory_html = f"<p class='advisory'>{_esc(advisory)}</p>" if advisory else ""
    return (
        f'<div id="app" data-version="{_esc(data["version"])}" '
        f'data-autotick="{autotick}" data-attempts-total="{_esc(data["attempts_total"])}">'
        f"<section class='band'><div class='inner'>"
        f"<div class='band-top'><p class='brandline'><strong>{_esc(BRAND)}</strong>"
        f" · {_esc(SUBTITLE)}</p>"
        f"<div class='band-tools'><span class='replay'>{_esc(_t(lang, 'replay'))}</span>"
        f"<span class='mode-switch'><a href='/' aria-current='true'>Replay</a>"
        f"<a href='/live'>Live</a></span>"
        f"<span class='lang'><a href='/?lang=en'{en_current}>EN</a>"
        f"<a href='/?lang=es'{es_current}>ES</a></span>"
        f"<form method='post' action='/panel/reset'>"
        f"<button class='btn ghost' type='submit'>{_t(lang, 'restart')}</button></form>"
        f"</div></div>"
        f"<div class='band-main'><div class='band-copy'>"
        f"<h1 aria-live='polite'>{html.escape(_t(lang, headline_key), quote=False)}</h1>"
        f"<p class='support'>{html.escape(support, quote=False)}</p>"
        f"{advisory_html}"
        f"<p class='attempts-label'>{_esc(attempts_label)}</p>"
        f"<div class='attempts'>{_status_blocks(data['attacker_statuses'])}</div>"
        f"</div>"
        f"<div class='clockbox'>{clock_html}"
        f"<p class='clock-note'>{_esc(_t(lang, 'real_incident'))}</p></div>"
        f"</div></div></section>"
        f"<section class='wrap decision'><h2>"
        f"{_t(lang, 'your_decision') if data['pending'] else _t(lang, 'what_happened')}</h2>"
        f"{_decision_html(state, lang)}</section>"
        f"<section class='wrap columns'>"
        f"<div class='col'><h2>{_t(lang, 'warehouse')}</h2>"
        f"<p class='bigline'>{_esc(warehouse_sub)}</p>"
        f"<div class='attempts small'>{_status_blocks(bodega_statuses, agent=True)}</div>"
        f"<p>{_esc(warehouse_note)}</p></div>"
        f"<div class='col'><h2>{_t(lang, 'attacker')}</h2>"
        f"<div id='attacker'>{_attacker_html(state, lang)}</div></div>"
        f"<p class='purchasing'>{_esc(_agent_display('compras', lang))} — "
        f"{_t(lang, 'untouched')}: {compras_block}</p>"
        f"</section>"
        f"<section class='wrap'><h2>{_t(lang, 'agents')}</h2>"
        f"<div id='agents'>{_agents_html(state, lang)}</div>"
        f"<h3>{_t(lang, 'anomalies')}</h3><ul>"
        + "".join(f"<li>{_esc(_anomaly_text(a, lang))}</li>" for a in anomalies)
        + ("</ul>" if anomalies else f"<li>{_t(lang, 'no_anomalies')}</li></ul>")
        + f"<h2>{_t(lang, 'decisions')}</h2>"
        f"<div id='decisions'>{_decisions_html(state, lang)}</div></section>"
        f"<section class='wrap'><h2>{_t(lang, 'models_run')}</h2>{_models_html(lang)}</section>"
        f"<footer class='wrap footer'>"
        f"<p>Built on Meta's Muse models; independent project, not affiliated "
        f"with or endorsed by Meta.</p>"
        f"<p>Built during the hackathon, 26 Oct – 4 Nov 2026.</p></footer>"
        f"</div>"
    )


_CSS = """
:root{--col:1140px}
@media (min-width:1600px){:root{--col:1320px}}
*{box-sizing:border-box}
body{margin:0;background:#EEF0EA;color:#1C2420;
font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.45}
h1,h2,h3{font-family:Georgia,"Times New Roman",serif;line-height:1.1}
h2{font-size:26px;margin:0 0 12px} h3{font-size:19px;margin:18px 0 8px}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
a{color:#1F7A4D} :focus-visible{outline:3px solid #E8A33D;outline-offset:2px}
.btn{display:inline-flex;align-items:center;justify-content:center;min-height:44px;
padding:10px 18px;border:2px solid #14201C;background:#EEF0EA;color:#14201C;
font:inherit;cursor:pointer;text-decoration:none}
.btn.primary{background:#1F7A4D;border-color:#1F7A4D;color:#fff}
.btn.secondary{background:#fff}
.btn.ghost{background:#14201C;border-color:#EEF0EA;color:#EEF0EA}
form{display:inline} .band form,.actions form{display:inline-block}
.band{background:#14201C;color:#EEF0EA}
.band .inner{width:min(var(--col),calc(100% - 40px));max-width:var(--col);
margin:0 auto;padding:18px 0 22px}
.band-top{display:flex;flex-wrap:wrap;gap:12px;align-items:center;
justify-content:space-between}
.brandline{margin:0;font-size:15px}
.band-tools{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.replay{font-size:13px;border:1px solid #EEF0EA;padding:9px 10px}
.mode-switch{display:inline-flex}
.mode-switch a{display:inline-flex;align-items:center;min-height:44px;
padding:8px 12px;color:#EEF0EA;border:1px solid #EEF0EA;text-decoration:none}
.mode-switch a[aria-current="true"]{background:#E8A33D;color:#14201C}
.lang{display:inline-flex}.lang a{display:inline-flex;align-items:center;
min-height:44px;padding:8px 12px;color:#EEF0EA;border:1px solid #EEF0EA;
text-decoration:none}.lang a[aria-current="true"]{background:#E8A33D;color:#14201C}
.band-main{display:flex;gap:28px;align-items:flex-start;justify-content:space-between}
.band-copy{max-width:760px}
.band h1{font-size:clamp(38px,5vw,64px);margin:20px 0 10px;font-weight:400}
.support{font-size:18px;margin:0 0 18px}
.advisory{font-size:13px;margin:0 0 14px;opacity:.85}
.attempts-label{margin:0 0 8px;font-size:15px}
.attempts{display:flex;flex-wrap:wrap;gap:8px}
.code-block{display:inline-flex;align-items:center;justify-content:center;
min-width:64px;min-height:52px;padding:8px 12px;font-size:22px;
font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.attempts.small .code-block{min-width:48px;min-height:44px;font-size:17px}
.code-200{background:#E8A33D;color:#14201C}
.code-agent-200{background:#1F7A4D;color:#fff}
.code-401{background:#B42318;color:#fff}
.code-none,.code-0{background:#EEF0EA;color:#14201C}
.attempts .code-block:last-child{animation:in .35s ease-out}
#app.no-new-attempt .attempts .code-block:last-child{animation:none}
@keyframes in{from{opacity:0}to{opacity:1}}
.clockbox{text-align:right;min-width:220px;padding-top:26px}
.clock-label{font-size:13px;margin:0;line-height:1.2}
#clock{font-family:Georgia,serif;font-size:clamp(34px,4vw,56px);margin:0;line-height:1.1}
.clock-note{margin:6px 0 0;font-size:15px}
.wrap{width:min(var(--col),calc(100% - 40px));max-width:var(--col);
margin:0 auto;padding:22px 0}
.decision{background:#fff;border-top:6px solid #1F7A4D;padding:22px 20px}
.decision-grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}
.plan{margin:0;padding-left:22px}.plan li{margin:8px 0}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px}
.voice-box label{display:block;font-weight:700;margin-bottom:6px}
.voice-box input{width:100%;min-height:44px;padding:10px;font:inherit;margin-bottom:10px}
.voice-notice{border:2px solid #E8A33D;background:#EEF0EA;padding:12px 14px;margin-top:12px}
.columns{display:grid;grid-template-columns:1fr 1fr;gap:0;padding-top:0}
.col{padding:20px;background:#fff}.col+.col{background:#14201C;color:#EEF0EA}
.bigline{font-family:Georgia,serif;font-size:24px}
.terminal{background:#000;color:#EEF0EA;padding:14px;overflow-wrap:anywhere}
.terminal p{margin:6px 0}
.term-401{background:#B42318;color:#fff;font-weight:700;padding:1px 5px}
#attacker form{display:block;margin:8px 0 0 -2px;padding:0}
.purchasing{grid-column:1/-1;margin:0;padding:14px 20px;background:#fff;
border-top:2px solid #14201C;font-size:17px}
.purchasing-code{min-width:48px;min-height:44px;font-size:17px;vertical-align:middle}
.decisions-total{margin:0 0 8px;font-size:14px}
.status{font-weight:700}.status-active{color:#1F7A4D}.status-revoked{color:#B42318}
.tablewrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;background:#fff}
td,th{border-bottom:1px solid #c9cec2;padding:9px 8px;text-align:left;vertical-align:top}
.feed{padding-left:20px}.feed li{margin:6px 0}
.footer{border-top:2px solid #14201C;font-size:14px}
@media (max-width:760px){.band-main,.decision-grid,.columns{grid-template-columns:1fr;
display:block}.col{margin-bottom:14px}.clockbox{text-align:left;padding-top:0}
.band h1{font-size:38px} td,th{padding:7px 5px;font-size:14px}}
@media (max-width:760px){.clock-label{margin-top:14px}}
@media (max-width:600px){.agents-table .col-models,.agents-table .col-token{display:none}
.agents-table td,.agents-table th{white-space:normal}}
@media (prefers-reduced-motion:reduce){.attempts .code-block:last-child{animation:none}
*{scroll-behavior:auto}}
"""

_JS = """
const clockState = {base: 0, at: Date.now(), running: false};
function fmtClock(total) {
  const s = Math.max(0, Math.floor(total));
  return String(Math.floor(s / 60)).padStart(2, "0") + ":" +
    String(s % 60).padStart(2, "0");
}
function readClock() {
  const el = document.getElementById("clock");
  if (!el) return;
  clockState.base = parseFloat(el.dataset.elapsed || "0");
  clockState.running = el.dataset.running === "1";
  clockState.at = Date.now();
}
function drawClock() {
  const el = document.getElementById("clock");
  if (!el || !clockState.running) return;
  el.textContent = fmtClock(clockState.base + (Date.now() - clockState.at) / 1000);
}
function replaceApp(html) {
  const old = document.getElementById("app");
  if (!old || !html.includes('id="app"') && !html.includes("id='app'")) return;
  const active = document.activeElement;
  const field = old.querySelector('input[name="transcript"]');
  const keep = field && active === field ?
    {value: field.value, start: field.selectionStart, end: field.selectionEnd} : null;
  const tpl = document.createElement("template");
  tpl.innerHTML = html.trim();
  const fresh = tpl.content.querySelector("#app");
  if (!fresh) return;
  const prevAttempts = parseInt(old.dataset.attemptsTotal || "0", 10);
  const newAttempts = parseInt(fresh.dataset.attemptsTotal || "0", 10);
  if (!(newAttempts > prevAttempts)) fresh.classList.add("no-new-attempt");
  old.replaceWith(fresh);
  readClock(); drawClock();
  if (keep) {
    const next = document.querySelector('input[name="transcript"]');
    if (next) {
      next.value = keep.value; next.focus();
      try { next.setSelectionRange(keep.start, keep.end); } catch (e) {}
    }
  }
}
document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  event.preventDefault();
  const url = form.getAttribute("action") || form.action;
  const res = await fetch(url, {method: "POST", body: new FormData(form),
    headers: {"X-Panel-Fetch": "1"}});
  replaceApp(await res.text());
});
async function pollLive() {
  if (document.hidden) return;
  const app = document.getElementById("app");
  if (!app) return;
  const res = await fetch("/panel/live?v=" + encodeURIComponent(app.dataset.version || "0"));
  if (res.status === 204 || !res.ok) return;
  replaceApp(await res.text());
}
async function autoTick() {
  if (document.hidden) return;
  const app = document.getElementById("app");
  if (!app || app.dataset.autotick !== "1") return;
  const res = await fetch("/panel/tick", {method: "POST",
    headers: {"X-Panel-Fetch": "1"}});
  if (res.ok) replaceApp(await res.text());
}
readClock(); drawClock();
setInterval(drawClock, 1000);
setInterval(pollLive, 2000);
setInterval(autoTick, 4000);
"""


def _resolve_lang(request: Request | None) -> str:
    if request is None:
        return "en"
    lang = request.query_params.get("lang") or request.cookies.get("panel_lang") or "en"
    return lang if lang in T else "en"


def _page(state: DemoState, lang: str = "en") -> str:
    favicon = (
        "data:image/svg+xml,%3Csvg viewBox='0 0 64 64'%3E"
        "%3Crect width='64' height='64' fill='%2314201C'/%3E"
        "%3Ctext x='32' y='42' font-family='Georgia,serif' font-size='28' "
        f"fill='%23E8A33D' text-anchor='middle'%3E{(BRAND[:1] or 'N')}%3C/text%3E%3C/svg%3E"
    )
    return (
        f"<!doctype html>\n<html lang='{_esc(lang)}'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{_esc(BRAND)} — {_esc(SUBTITLE)}</title>"
        f"<link rel='icon' href=\"{favicon}\">"
        f"<style>{_CSS}</style></head><body><main>{_app_html(state, lang)}</main>"
        f"<script>{_JS}</script></body></html>"
    )


def create_panel_app(state: DemoState | None = None, *, live_chain: Any = None) -> FastAPI:
    demo = state or build_replay_state()
    app = FastAPI(title=f"{BRAND} — panel", version="0.1.0")
    app.state.demo = demo
    app.state.live_chain = live_chain
    channel = WhatsAppChannel(demo.broker)
    app.state.whatsapp = channel
    app.include_router(whatsapp_router(channel))

    def _with_cookie(resp: HTMLResponse, request: Request, lang: str) -> HTMLResponse:
        if request.query_params.get("lang") in T:
            resp.set_cookie("panel_lang", lang, max_age=2592000, path="/", samesite="lax")
        return resp

    def _post_response(request: Request, status_code: int = 200) -> HTMLResponse:
        lang = _resolve_lang(request)
        if request.headers.get("x-panel-fetch") == "1":
            resp = HTMLResponse(_app_html(demo, lang), status_code=status_code)
        else:
            resp = HTMLResponse(_page(demo, lang), status_code=status_code)
        return _with_cookie(resp, request, lang)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        demo.start_clock()
        lang = _resolve_lang(request)
        return _with_cookie(HTMLResponse(_page(demo, lang)), request, lang)

    @app.get("/panel/state")
    async def panel_state() -> JSONResponse:
        return JSONResponse(demo.public())

    @app.get("/panel/decisions", response_class=HTMLResponse)
    async def decisions(request: Request) -> HTMLResponse:
        return HTMLResponse(_decisions_html(demo, _resolve_lang(request)))

    @app.get("/panel/incidents", response_class=HTMLResponse)
    async def incidents(request: Request) -> HTMLResponse:
        return HTMLResponse(_incidents_html(demo, _resolve_lang(request)))

    @app.get("/panel/attacker", response_class=HTMLResponse)
    async def attacker(request: Request) -> HTMLResponse:
        return HTMLResponse(_attacker_html(demo, _resolve_lang(request)))

    @app.get("/panel/live")
    async def live(request: Request, v: int = 0) -> Response:
        if v == demo.version:
            return Response(status_code=204)
        return HTMLResponse(_app_html(demo, _resolve_lang(request)))

    @app.post("/panel/approve/{approval_id}", response_class=HTMLResponse)
    async def approve(approval_id: str, request: Request) -> HTMLResponse:
        try:
            demo.approve_and_execute(approval_id)
        except (KeyError, ValueError) as exc:
            return HTMLResponse(f"<p>Error: {_esc(exc)}</p>", status_code=400)
        return _post_response(request)

    @app.post("/panel/reject/{approval_id}", response_class=HTMLResponse)
    async def reject(approval_id: str, request: Request) -> HTMLResponse:
        try:
            demo.reject(approval_id)
        except (KeyError, ValueError) as exc:
            return HTMLResponse(f"<p>Error: {_esc(exc)}</p>", status_code=400)
        return _post_response(request)

    @app.post("/panel/attacker/probe", response_class=HTMLResponse)
    async def probe(request: Request) -> HTMLResponse:
        demo.probe_attacker()
        return _post_response(request)

    @app.post("/panel/voice", response_class=HTMLResponse)
    async def voice(
        request: Request,
        approval_id: str = Form(...),
        transcript: str = Form(...),
        confirmed: bool = Form(False),
    ) -> HTMLResponse:
        existed = demo.broker.get(approval_id) is not None
        demo.handle_voice(approval_id, transcript, confirmed=False)
        if not existed:
            return HTMLResponse(
                f"<p>Error: aprobación no encontrada: {_esc(approval_id)}</p>",
                status_code=400,
            )
        return _post_response(request)

    @app.post("/panel/voice/confirm", response_class=HTMLResponse)
    async def voice_confirm(request: Request, approval_id: str = Form(...)) -> HTMLResponse:
        existed = demo.broker.get(approval_id) is not None
        demo.confirm_voice(approval_id)
        if not existed:
            return HTMLResponse(
                f"<p>Error: aprobación no encontrada: {_esc(approval_id)}</p>",
                status_code=400,
            )
        return _post_response(request)

    @app.post("/panel/voice/cancel", response_class=HTMLResponse)
    async def voice_cancel(request: Request, approval_id: str = Form(...)) -> HTMLResponse:
        existed = demo.broker.get(approval_id) is not None
        demo.cancel_voice(approval_id)
        if not existed:
            return HTMLResponse(
                f"<p>Error: aprobación no encontrada: {_esc(approval_id)}</p>",
                status_code=400,
            )
        return _post_response(request)

    @app.post("/panel/reset", response_class=HTMLResponse)
    async def reset(request: Request) -> HTMLResponse:
        if os.environ.get("DEMO", "replay") not in ("replay", "live"):
            return HTMLResponse("<p>Error: reset solo disponible en replay</p>", status_code=403)
        fresh = build_replay_state()
        fresh.version = demo.version + 1
        demo.__dict__.update(fresh.__dict__)
        channel.broker = demo.broker
        app.state.whatsapp = channel
        if request.headers.get("x-panel-fetch") == "1":
            # El reinicio vino de la página abierta: el dueño ya ve el incidente.
            demo.start_clock()
        return _post_response(request)

    @app.post("/panel/tick", response_class=HTMLResponse)
    async def tick(request: Request) -> HTMLResponse:
        demo.tick()
        return _post_response(request)

    # -- modo live (H14): solo DEMO=live y solo loopback --------------------
    def _live_guard(request: Request) -> JSONResponse | None:
        if os.environ.get("DEMO", "replay") != "live":
            return JSONResponse(
                {"error": "live mode only enabled with DEMO=live"},
                status_code=403,
            )
        host = request.client.host if request.client else ""
        if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
            return JSONResponse(
                {"error": "live mode only accepts loopback clients (127.0.0.1/::1)"},
                status_code=403,
            )
        return None

    def _get_chain() -> Any:
        chain = getattr(app.state, "live_chain", None)
        if chain is None:
            from web.live_chain import LiveChain

            chain = LiveChain.start()
            app.state.live_chain = chain
        return chain

    @app.get("/live", response_class=HTMLResponse)
    def live_page(request: Request) -> Any:
        lang = _resolve_lang(request)
        if os.environ.get("DEMO", "replay") != "live":
            return _with_cookie(
                HTMLResponse(render_live_inactive_page(lang)), request, lang
            )
        guard = _live_guard(request)
        if guard is not None:
            return guard
        spark_open_no_key = True
        no_key = False
        try:
            chain_obj = getattr(app.state, "live_chain", None)
            vault_obj = getattr(chain_obj, "vault", None) if chain_obj is not None else None
            if vault_obj is None:
                from shield.vault.vault import get_vault

                vault_obj = get_vault()
            try:
                spark_open_no_key = not bool(vault_obj.get("baseten-api-key"))
            except Exception:
                spark_open_no_key = True
            try:
                no_key = not bool(vault_obj.get("META_MODEL_API_KEY"))
            except Exception:
                no_key = True
        except Exception:
            spark_open_no_key = True
        return _with_cookie(
            HTMLResponse(
                render_live_page(lang, spark_open_no_key=spark_open_no_key, no_key=no_key)
            ),
            request,
            lang,
        )

    @app.post("/live/start")
    def live_start(request: Request) -> Any:
        guard = _live_guard(request)
        if guard is not None:
            return guard
        return JSONResponse(_get_chain().state())

    @app.post("/live/reset")
    def live_reset(request: Request) -> Any:
        guard = _live_guard(request)
        if guard is not None:
            return guard
        chain = getattr(app.state, "live_chain", None)
        if chain is None:
            return JSONResponse(_get_chain().state())
        return JSONResponse(chain.reset())

    @app.post("/live/step/{name}")
    def live_step(
        name: str, request: Request, file: UploadFile | None = File(None)
    ) -> Any:
        guard = _live_guard(request)
        if guard is not None:
            return guard
        steps = {"invoice", "count", "attack", "guardian", "contain"}
        if name not in steps:
            return JSONResponse({"error": f"unknown live step: {name}"}, status_code=404)
        chain = getattr(app.state, "live_chain", None)
        if chain is None:
            return JSONResponse(
                {"error": "live chain not started: POST /live/start first"},
                status_code=409,
            )
        if name == "count":
            image_bytes = file.file.read() if file is not None else None
            return JSONResponse(chain.step_count(image_bytes))
        return JSONResponse(getattr(chain, f"step_{name}")())

    @app.post("/live/voice")
    def live_voice(
        request: Request,
        file: UploadFile | None = File(None),
        typed: str | None = Form(None),
    ) -> Any:
        guard = _live_guard(request)
        if guard is not None:
            return guard
        chain = getattr(app.state, "live_chain", None)
        if chain is None:
            return JSONResponse(
                {"error": "live chain not started: POST /live/start first"},
                status_code=409,
            )
        wav_bytes = file.file.read() if file is not None else None
        return JSONResponse(chain.step_voice(wav_bytes=wav_bytes, typed=typed))

    @app.post("/live/voice/confirm")
    def live_voice_confirm(request: Request) -> Any:
        guard = _live_guard(request)
        if guard is not None:
            return guard
        chain = getattr(app.state, "live_chain", None)
        if chain is None:
            return JSONResponse({"error": "live chain not started"}, status_code=409)
        return JSONResponse(chain.step_voice_confirm())

    @app.post("/live/voice/cancel")
    def live_voice_cancel(request: Request) -> Any:
        guard = _live_guard(request)
        if guard is not None:
            return guard
        chain = getattr(app.state, "live_chain", None)
        if chain is None:
            return JSONResponse({"error": "live chain not started"}, status_code=409)
        return JSONResponse(chain.step_voice_cancel())

    @app.get("/live/state")
    def live_state(request: Request) -> Any:
        guard = _live_guard(request)
        if guard is not None:
            return guard
        chain = getattr(app.state, "live_chain", None)
        if chain is None:
            return JSONResponse({"status": "not_started", "results": {}, "provenance": []})
        return JSONResponse(chain.state())

    @app.get("/live/provenance.json")
    def live_provenance(request: Request) -> Any:
        guard = _live_guard(request)
        if guard is not None:
            return guard
        chain = getattr(app.state, "live_chain", None)
        if chain is None:
            return JSONResponse({"error": "live chain not started"}, status_code=409)
        return Response(
            content=chain.export(),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=provenance.json"},
        )

    @app.get("/live/fixture/{kind}")
    def live_fixture(kind: str, request: Request) -> Any:
        guard = _live_guard(request)
        if guard is not None:
            return guard
        names = {"invoice": "invoice-poisoned.png", "shelf": "shelf-boxes.png"}
        filename = names.get(kind)
        if filename is None:
            return JSONResponse({"error": f"unknown fixture: {kind}"}, status_code=404)
        path = Path(__file__).resolve().parents[1] / "evals" / "fixtures" / "live" / filename
        return Response(content=path.read_bytes(), media_type="image/png")

    @app.get("/health")
    async def health() -> PlainTextResponse:
        return PlainTextResponse("ok")

    return app


app = create_panel_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8001")))
