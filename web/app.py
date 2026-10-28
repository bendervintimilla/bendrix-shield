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
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from channels.approvals import ApprovalBroker, ChannelApprover
from channels.voice import VoiceApprovalFlow
from channels.whatsapp import WhatsAppChannel
from channels.whatsapp import create_router as whatsapp_router
from shield.actions import Actions
from shield.agent import GuardianAgent, RunbookGuardianActions
from shield.registry import Registry
from shield.schemas import CallLog
from shield.sdk.token_store import InMemoryTokenStore

UPSTREAM_KEY = "upstream-demo-key-0000"


def _esc(value: Any) -> str:
    return html.escape(str(value))


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
    executed: list[dict[str, Any]] = field(default_factory=list)
    started_monotonic: float = field(default_factory=time.monotonic)
    incident_at: str = ""

    def elapsed_s(self) -> float:
        return round(time.monotonic() - self.started_monotonic, 1)

    def probe_attacker(self) -> int:
        from sandbox.attacker import attempt_statuses

        statuses = attempt_statuses(self.gateway, self.attacker_raw, attempts=1)
        self.attacker_statuses.extend(statuses)
        return statuses[0] if statuses else 0

    def approve_and_execute(self, approval_id: str) -> dict[str, Any]:
        if self.broker.get(approval_id) and self.broker.get(approval_id).status == "pending":  # type: ignore[union-attr]
            self.broker.approve(approval_id)
        report = self.guardian.execute_approved(approval_id)
        self.executed = report.executed
        self.probe_attacker()
        return {"approval_id": approval_id, "executed": report.executed, "summary": report.summary}

    def reject(self, approval_id: str) -> dict[str, Any]:
        self.broker.reject(approval_id)
        self.probe_attacker()
        return {"approval_id": approval_id, "status": "rejected"}

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
    registry.create_token("compras", "crew", models=["muse-spark-1.3"])
    store.set_token("bodega", bodega_raw, bodega.token_id)
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
    return state


def _agents_html(state: DemoState) -> str:
    rows = "".join(
        f"<tr><td>{_esc(t.agent)}</td><td>{_esc(t.app)}</td><td>{_esc(t.token_id)}</td>"
        f"<td>{_esc(t.status.value)}</td><td>{_esc(', '.join(t.models))}</td></tr>"
        for t in state.registry.list_tokens()
    )
    return f"<table><thead><tr><th>Agente</th><th>App</th><th>Token</th><th>Estado</th><th>Modelos</th></tr></thead><tbody>{rows}</tbody></table>"


def _decisions_html(state: DemoState) -> str:
    items = "".join(
        f"<li>{_esc(c.ts.time())} · {_esc(c.agent)} · {_esc(c.model)} · "
        f"{_esc(c.decision.value)} · {_esc(c.src_country or '—')}</li>"
        for c in state.registry.list_calls()
    )
    return f"<ul class='feed'>{items or '<li>Sin llamadas todavía.</li>'}</ul>"


def _incidents_html(state: DemoState) -> str:
    data = state.public()
    anomalies = "".join(
        f"<li>{_esc(a.get('kind'))}: {_esc(a.get('agent'))} — {_esc(a.get('detail'))}</li>"
        for a in data["incidents"]["anomalies"]
    )
    exposures = "".join(
        f"<li>{_esc(e.get('threat_id'))} × {_esc(e.get('asset_id'))} "
        f"({_esc(e.get('confidence'))}): {_esc(e.get('reason'))}</li>"
        for e in data["incidents"]["exposures"]
    )
    pending = ""
    for req in data["pending"]:
        aid = _esc(req["approval_id"])
        steps = "".join(
            f"<li>{_esc(s.get('action'))} → {_esc(s.get('target'))}: {_esc(s.get('reason'))}</li>"
            for s in (req["plan"].get("steps") or [])
        )
        pending += (
            f"<div class='approval'><p><strong>{aid}</strong> · {_esc(req['plan'].get('summary', ''))}</p>"
            f"<ul>{steps}</ul>"
            f"<form method='post' action='/panel/approve/{aid}' hx-post='/panel/approve/{aid}' hx-target='#incidents'>"
            f"<button type='submit'>Aprobar</button></form> "
            f"<form method='post' action='/panel/reject/{aid}' hx-post='/panel/reject/{aid}' hx-target='#incidents'>"
            f"<button type='submit'>Rechazar</button></form> "
            f"<form method='post' action='/panel/voice' hx-post='/panel/voice' hx-target='#incidents'>"
            f"<input type='hidden' name='approval_id' value='{aid}'>"
            f"<input name='transcript' value='sí, rota todo' aria-label='Orden de voz (transcripción)'>"
            f"<button type='submit'>Enviar voz</button></form></div>"
        )
    executed = "".join(
        f"<li>{_esc(e.get('action'))} {_esc(e.get('target'))}: {_esc(e.get('status'))}</li>"
        for e in data["executed"]
    )
    return (
        f"<h3>Anomalías</h3><ul>{anomalies or '<li>Ninguna.</li>'}</ul>"
        f"<h3>Exposición</h3><ul>{exposures or '<li>Sin exposición confirmada en replay.</li>'}</ul>"
        f"{pending}<h3>Ejecutado</h3><ul>{executed or '<li>Nada ejecutado todavía.</li>'}</ul>"
    )


def _attacker_html(state: DemoState) -> str:
    from sandbox.attacker import format_timeline

    timeline = format_timeline(state.attacker_statuses) or "—"
    return (
        f"<div class='terminal'><p>$ attacker.py --token shd_bodega_… (robado)</p>"
        f"<p>{_esc(timeline)}</p></div>"
        f"<form method='post' action='/panel/attacker/probe' hx-post='/panel/attacker/probe' "
        f"hx-target='#attacker'><button type='submit'>Reintentar como atacante</button></form>"
    )


def _page(state: DemoState) -> str:
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bendrix Shield — panel</title>
<script src="https://unpkg.com/htmx.org@2.0.4"></script>
<style>
body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:0;background:#eef0ea;color:#1c2420}}
header{{background:#1c2420;color:#f2f2ea;padding:20px 28px}} header h1{{font-family:Georgia,serif;margin:0;font-size:28px}}
header p{{margin:6px 0 0;color:#c8cec4}} main{{max-width:1080px;margin:0 auto;padding:20px}}
section{{background:#fff;border:1px solid #d4d8cf;padding:16px 20px;margin:0 0 16px}}
h2{{font-family:Georgia,serif;margin-top:0}} table{{border-collapse:collapse;width:100%}} td,th{{border-bottom:1px solid #e2e5dc;padding:6px 8px;text-align:left}}
.terminal{{background:#101312;color:#9fd89f;font-family:ui-monospace,Menlo,monospace;padding:12px 14px}}
button{{background:#1f6f4a;color:#fff;border:0;padding:8px 14px;cursor:pointer}} form{{display:inline}}
.feed li{{margin:4px 0}} #clock{{font-family:ui-monospace,Menlo,monospace;font-size:22px}}
</style></head><body>
<header><h1>Bendrix Shield</h1><p>Panel del dueño · DEMO={_esc(os.environ.get("DEMO", "replay"))} · incidente {_esc(state.incident_at)}</p>
<p>Tiempo desde el incidente: <span id="clock">00:00</span></p></header>
<main>
<section><h2>Apps y agentes conectados</h2><div id="agents">{_agents_html(state)}</div></section>
<section><h2>Decisiones de la política en vivo</h2><div id="decisions" hx-get="/panel/decisions" hx-trigger="every 3s">{_decisions_html(state)}</div></section>
<section><h2>Incidentes y aprobación</h2><div id="incidents">{_incidents_html(state)}</div></section>
<section><h2>Terminal del atacante</h2><div id="attacker">{_attacker_html(state)}</div></section>
</main>
<script>
const started = Date.now() - {int(state.elapsed_s() * 1000)};
function tick(){{const s = Math.floor((Date.now() - started) / 1000);
document.getElementById('clock').textContent = String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');}}
tick(); setInterval(tick, 1000);
</script></body></html>"""


def create_panel_app(state: DemoState | None = None) -> FastAPI:
    demo = state or build_replay_state()
    app = FastAPI(title="Bendrix Shield — panel", version="0.1.0")
    app.state.demo = demo
    channel = WhatsAppChannel(demo.broker)
    app.state.whatsapp = channel
    app.include_router(whatsapp_router(channel))

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return HTMLResponse(_page(demo))

    @app.get("/panel/state")
    async def panel_state() -> JSONResponse:
        return JSONResponse(demo.public())

    @app.get("/panel/decisions", response_class=HTMLResponse)
    async def decisions() -> HTMLResponse:
        return HTMLResponse(_decisions_html(demo))

    @app.get("/panel/incidents", response_class=HTMLResponse)
    async def incidents() -> HTMLResponse:
        return HTMLResponse(_incidents_html(demo))

    @app.get("/panel/attacker", response_class=HTMLResponse)
    async def attacker() -> HTMLResponse:
        return HTMLResponse(_attacker_html(demo))

    @app.post("/panel/approve/{approval_id}", response_class=HTMLResponse)
    async def approve(approval_id: str) -> HTMLResponse:
        try:
            demo.approve_and_execute(approval_id)
        except (KeyError, ValueError) as exc:
            return HTMLResponse(f"<p>Error: {_esc(exc)}</p>", status_code=400)
        return HTMLResponse(_incidents_html(demo))

    @app.post("/panel/reject/{approval_id}", response_class=HTMLResponse)
    async def reject(approval_id: str) -> HTMLResponse:
        try:
            demo.reject(approval_id)
        except (KeyError, ValueError) as exc:
            return HTMLResponse(f"<p>Error: {_esc(exc)}</p>", status_code=400)
        return HTMLResponse(_incidents_html(demo))

    @app.post("/panel/attacker/probe", response_class=HTMLResponse)
    async def probe() -> HTMLResponse:
        demo.probe_attacker()
        return HTMLResponse(_attacker_html(demo))

    @app.post("/panel/voice", response_class=HTMLResponse)
    async def voice(
        approval_id: str = Form(...), transcript: str = Form(...), confirmed: bool = Form(False)
    ) -> HTMLResponse:
        flow = VoiceApprovalFlow(demo.broker)
        outcome = flow.handle_transcript(approval_id, transcript, confirmed=confirmed)
        if outcome.get("status") == "approved":
            report = demo.guardian.execute_approved(approval_id)
            demo.executed = report.executed
            demo.probe_attacker()
        return HTMLResponse(_incidents_html(demo))

    @app.get("/health")
    async def health() -> PlainTextResponse:
        return PlainTextResponse("ok")

    return app


app = create_panel_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8001")))
