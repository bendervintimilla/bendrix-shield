"""Gateway compatible con OpenAI de Bendrix Shield.

Recibe ``Authorization: Bearer [REDACTED]…``, valida estado/modelo/tope/ritmo,
pasa el payload por ``gate.check`` y reenvía a la Meta Model API con la llave
real del vault (la app nunca la ve). Registra cada llamada como ``CallLog``.

Rutas upstream verificadas (docs/MODELS.md): ``/v1/chat/completions``,
``/v1/responses`` (por ahí va SAM 3.1, con ``model="sam-3.1"``: no hay ruta
SAM separada en la doc) y ``/v1/asr/transcribe`` para voz, expuesta aquí con
la forma OpenAI ``/v1/audio/transcriptions``.
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from shield.gate.check import check as gate_check
from shield.gateway.geo import country_for_ip
from shield.meta_client import BASE_URL, compute_cost_usd
from shield.registry import Registry
from shield.schemas import AgentToken, AgentTokenStatus, CallLog, Decision
from shield.vault.vault import BaseVault, get_vault

UPSTREAM_KEY_NAME = "META_MODEL_API_KEY"
DEFAULT_RATE_LIMIT_PER_MINUTE = 60


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": "shield_error", "code": code}},
    )


class RateLimiter:
    """Ventana deslizante de 60 s por token_id."""

    def __init__(self, limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE) -> None:
        self.limit = limit_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, token_id: str, now: float | None = None) -> bool:
        if self.limit <= 0:
            return False
        ts = time.monotonic() if now is None else now
        hits = self._hits[token_id]
        while hits and hits[0] <= ts - 60.0:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(ts)
        return True


def _usage(data: dict[str, Any]) -> tuple[int, int, dict[str, Any]]:
    usage = data.get("usage") or {}
    tokens_in = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    tokens_out = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    return tokens_in, tokens_out, usage


def create_app(
    *,
    registry: Registry | None = None,
    vault: BaseVault | None = None,
    upstream_base_url: str = BASE_URL,
    upstream_transport: httpx.BaseTransport | None = None,
    sandbox: bool | None = None,
    rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE,
) -> FastAPI:
    reg = registry or Registry()
    vlt = vault or get_vault()
    is_sandbox = sandbox if sandbox is not None else os.environ.get("SHIELD_SANDBOX") == "1"
    limiter = RateLimiter(rate_limit_per_minute)
    app = FastAPI(title="Bendrix Shield Gateway", version="0.1.0")
    app.state.registry = reg
    app.state.vault = vlt

    def authenticate(request: Request) -> AgentToken | JSONResponse:
        header = request.headers.get("authorization", "")
        raw = header[7:].strip() if header.lower().startswith("bearer ") else ""
        token = reg.authenticate(raw)
        if token is None:
            return _error(401, "invalid_token", "Invalid Shield token")
        if token.status is AgentTokenStatus.REVOKED:
            return _error(401, "revoked_token", "Shield token revoked")
        if token.status is not AgentTokenStatus.ACTIVE:
            return _error(401, "rotated_token", "Shield token rotated; use the new token")
        return token

    def preflight(request: Request, token: AgentToken, model: str) -> JSONResponse | None:
        if token.models and model not in token.models:
            return _error(403, "model_not_allowed", f"Model {model} not allowed for this agent")
        if (
            token.spend_cap_usd is not None
            and reg.total_spend_usd(token.agent) >= token.spend_cap_usd
        ):
            return _error(403, "spend_cap_exceeded", "Spend cap exceeded for this agent")
        if not limiter.allow(token.token_id):
            resp = _error(429, "rate_limit_exceeded", "Rate limit exceeded for this token")
            resp.headers["Retry-After"] = "60"
            return resp
        return None

    def country(request: Request) -> str | None:
        if is_sandbox:
            demo = request.headers.get("x-demo-country")
            if demo:
                return demo.upper()[:2]
        return country_for_ip(request.client.host if request.client else None)

    def log_call(
        request: Request,
        token: AgentToken,
        model: str,
        *,
        decision: Decision,
        started: float,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost: float = 0.0,
    ) -> None:
        reg.record_call(
            CallLog(
                ts=datetime.now(UTC),
                agent=token.agent,
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost,
                latency_ms=(time.perf_counter() - started) * 1000,
                src_ip=request.client.host if request.client else None,
                src_country=country(request),
                decision=decision,
            )
        )

    def upstream_key() -> str | None:
        try:
            return vlt.get(UPSTREAM_KEY_NAME)
        except Exception:
            return None

    def map_upstream_error(resp: httpx.Response) -> JSONResponse:
        if resp.status_code in (401, 402, 403):
            return _error(
                503, "needs_credits", "Upstream needs credits or a valid key (needs_credits)"
            )
        return JSONResponse(
            status_code=resp.status_code,
            content={
                "error": {
                    "message": "upstream error",
                    "type": "shield_error",
                    "code": "upstream_error",
                }
            },
        )

    async def forward_json(
        request: Request, token: AgentToken, path: str, payload: dict[str, Any]
    ) -> Any:
        started = time.perf_counter()
        model = str(payload.get("model") or "")
        blocked = preflight(request, token, model)
        if blocked is not None:
            log_call(request, token, model, decision=Decision.BLOCK, started=started)
            return blocked
        gate = gate_check(payload)
        if not gate.allowed:
            log_call(request, token, model, decision=Decision.BLOCK, started=started)
            return _error(403, "gate_blocked", "Payload blocked by Shield gate (canary)")
        forward_payload = gate.redacted if isinstance(gate.redacted, dict) else payload
        key = upstream_key()
        if not key:
            log_call(request, token, model, decision=Decision.BLOCK, started=started)
            return _error(503, "needs_credits", "Upstream key missing in vault (needs_credits)")
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        stream = bool(forward_payload.get("stream"))
        async with httpx.AsyncClient(
            base_url=upstream_base_url, transport=upstream_transport, timeout=120.0
        ) as client:
            if stream:
                return await _forward_stream(
                    client, request, token, path, forward_payload, headers, started, log_call
                )
            try:
                resp = await client.post(path, json=forward_payload, headers=headers)
            except httpx.HTTPError:
                log_call(request, token, model, decision=Decision.BLOCK, started=started)
                return _error(502, "upstream_unreachable", "Upstream unreachable")
        if resp.status_code >= 400:
            log_call(request, token, model, decision=Decision.BLOCK, started=started)
            return map_upstream_error(resp)
        data = resp.json()
        tokens_in, tokens_out, usage = _usage(data)
        out_gate = gate_check(data)
        if not out_gate.allowed:
            log_call(request, token, model, decision=Decision.BLOCK, started=started)
            return _error(502, "gate_blocked_response", "Upstream response blocked by Shield gate")
        body = out_gate.redacted if isinstance(out_gate.redacted, dict) else data
        cost = compute_cost_usd(model, usage)
        log_call(
            request,
            token,
            model,
            decision=Decision.ALLOW,
            started=started,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost=cost,
        )
        return JSONResponse(content=body)

    async def _forward_stream(
        client: httpx.AsyncClient,
        request: Request,
        token: AgentToken,
        path: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        started: float,
        log_call_fn: Any,
    ) -> Any:
        model = str(payload.get("model") or "")
        try:
            upstream_req = client.build_request("POST", path, json=payload, headers=headers)
            resp = await client.send(upstream_req, stream=True)
        except httpx.HTTPError:
            log_call_fn(request, token, model, decision=Decision.BLOCK, started=started)
            return _error(502, "upstream_unreachable", "Upstream unreachable")
        if resp.status_code >= 400:
            await resp.aclose()
            log_call_fn(request, token, model, decision=Decision.BLOCK, started=started)
            return map_upstream_error(resp)

        async def chunks() -> Any:
            tokens_in = tokens_out = 0
            cost = 0.0
            blocked = False
            try:
                async for raw in resp.aiter_bytes():
                    text = raw.decode("utf-8", errors="ignore")
                    result = gate_check(text)
                    if not result.allowed:
                        blocked = True
                        yield (
                            b'data: {"error":{"code":"gate_blocked",'
                            b'"message":"stream blocked by Shield gate"}}\n\n'
                        )
                        break
                    for line in text.splitlines():
                        if line.startswith("data: ") and line[6:] not in ("", "[DONE]"):
                            try:
                                event = json.loads(line[6:])
                            except json.JSONDecodeError:
                                continue
                            ti, to, usage = _usage(event)
                            tokens_in, tokens_out = ti or tokens_in, to or tokens_out
                            if usage:
                                cost = compute_cost_usd(model, usage)
                    yield (redact_stream_text(text) if result.redactions else raw)
            finally:
                await resp.aclose()
                log_call_fn(
                    request,
                    token,
                    model,
                    decision=Decision.BLOCK if blocked else Decision.ALLOW,
                    started=started,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost=cost,
                )

        return StreamingResponse(
            chunks(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    def redact_stream_text(text: str) -> bytes:
        from shield.gate.redact import redact_text

        redacted, _ = redact_text(text)
        return redacted.encode("utf-8")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Any:
        token = authenticate(request)
        if isinstance(token, JSONResponse):
            return token
        payload = await request.json()
        return await forward_json(request, token, "/chat/completions", payload)

    @app.post("/v1/responses")
    async def responses(request: Request) -> Any:
        token = authenticate(request)
        if isinstance(token, JSONResponse):
            return token
        payload = await request.json()
        # SAM 3.1 va por esta misma ruta con model="sam-3.1" (docs/MODELS.md).
        return await forward_json(request, token, "/responses", payload)

    @app.post("/v1/audio/transcriptions")
    async def transcriptions(
        request: Request,
        file: UploadFile = File(...),
        model: str = Form("muse-voice-transcribe-1.0"),
    ) -> Any:
        started = time.perf_counter()
        token = authenticate(request)
        if isinstance(token, JSONResponse):
            return token
        blocked = preflight(request, token, model)
        if blocked is not None:
            log_call(request, token, model, decision=Decision.BLOCK, started=started)
            return blocked
        audio = await file.read()
        gate = gate_check({"model": model, "file": file.filename or ""})
        if not gate.allowed:
            log_call(request, token, model, decision=Decision.BLOCK, started=started)
            return _error(403, "gate_blocked", "Payload blocked by Shield gate (canary)")
        key = upstream_key()
        if not key:
            log_call(request, token, model, decision=Decision.BLOCK, started=started)
            return _error(503, "needs_credits", "Upstream key missing in vault (needs_credits)")
        request_obj = {"mode": "PUSH_TO_TALK", "model": model, "audioEncoding": "WAV"}
        files = {
            "request": (None, json.dumps(request_obj), "application/json"),
            "audio": (file.filename or "audio.wav", audio, file.content_type or "audio/wav"),
        }
        async with httpx.AsyncClient(
            base_url=upstream_base_url, transport=upstream_transport, timeout=120.0
        ) as client:
            try:
                resp = await client.post(
                    "/asr/transcribe", files=files, headers={"Authorization": f"Bearer {key}"}
                )
            except httpx.HTTPError:
                log_call(request, token, model, decision=Decision.BLOCK, started=started)
                return _error(502, "upstream_unreachable", "Upstream unreachable")
        if resp.status_code >= 400:
            log_call(request, token, model, decision=Decision.BLOCK, started=started)
            return map_upstream_error(resp)
        data = resp.json()
        cost = compute_cost_usd(model, data)
        log_call(request, token, model, decision=Decision.ALLOW, started=started, cost=cost)
        text = data.get("transcript") or data.get("text") or ""
        out_gate = gate_check(text)
        if not out_gate.allowed:
            return _error(502, "gate_blocked_response", "Upstream response blocked by Shield gate")
        redacted_text = out_gate.redacted if isinstance(out_gate.redacted, str) else text
        return {"text": redacted_text, **({} if redacted_text == text else {})}

    return app


def main() -> None:  # pragma: no cover - arranque manual
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8000)


if __name__ == "__main__":  # pragma: no cover
    main()
