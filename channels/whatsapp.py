"""Canal WhatsApp (H8): webhook verificado, botones y simulador.

Protocolo según la doc de Meta WhatsApp Business Platform: verificación
``GET`` con ``hub.mode``/``hub.verify_token``/``hub.challenge`` y ``POST``
firmado con ``X-Hub-Signature-256`` (HMAC-SHA256 del cuerpo con el secreto
de la app). Los botones interactivos usan ids ``approve:<approval_id>``,
``reject:<approval_id>`` y ``detail:<approval_id>``.

El número de prueba y el token salen del vault como ``whatsapp-test-*``.
Si no existen, el canal queda en modo simulador: los mensajes salientes se
guardan en ``outbox`` y el panel web es el canal operativo. Ningún secreto
se loguea ni sale en payloads públicos.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from channels.approvals import ApprovalBroker

GRAPH_URL = "https://graph.facebook.com/v21.0"


def verify_signature(body: bytes, signature: str | None, app_secret: str) -> bool:
    if not signature or not app_secret:
        return False
    expected = "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


@dataclass
class WhatsAppMessage:
    message_id: str
    from_number: str = ""
    kind: str = "text"  # text | button | audio
    text: str = ""
    button_id: str = ""
    button_title: str = ""
    audio_id: str = ""


def parse_webhook(payload: dict[str, Any]) -> list[WhatsAppMessage]:
    messages: list[WhatsAppMessage] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for raw in value.get("messages") or []:
                msg = WhatsAppMessage(
                    message_id=str(raw.get("id", "")),
                    from_number=str(raw.get("from", "")),
                )
                interactive = raw.get("interactive") or {}
                reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
                if reply:
                    msg.kind = "button"
                    msg.button_id = str(reply.get("id", ""))
                    msg.button_title = str(reply.get("title", ""))
                elif raw.get("type") == "audio" or raw.get("audio"):
                    msg.kind = "audio"
                    msg.audio_id = str((raw.get("audio") or {}).get("id", ""))
                else:
                    msg.text = str((raw.get("text") or {}).get("body", ""))
                messages.append(msg)
    return messages


def button_payload(to: str, approval_id: str, summary: str) -> dict[str, Any]:
    """Mensaje interactivo con Aprobar / Rechazar / Ver detalle."""
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": summary[:1024]},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": f"approve:{approval_id}", "title": "Aprobar"},
                    },
                    {
                        "type": "reply",
                        "reply": {"id": f"reject:{approval_id}", "title": "Rechazar"},
                    },
                    {
                        "type": "reply",
                        "reply": {"id": f"detail:{approval_id}", "title": "Ver detalle"},
                    },
                ]
            },
        },
    }


def simulated_click_payload(
    *, approval_id: str, action: str, message_id: str, from_number: str = "593990000000"
) -> dict[str, Any]:
    """Payload tal como lo enviaría Meta al pulsar un botón (simulador)."""
    titles = {"approve": "Aprobar", "reject": "Rechazar", "detail": "Ver detalle"}
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "id": message_id,
                                    "from": from_number,
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button_reply",
                                        "button_reply": {
                                            "id": f"{action}:{approval_id}",
                                            "title": titles.get(action, action),
                                        },
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ],
    }


@dataclass
class WhatsAppConfig:
    phone_number: str | None = None
    token: str | None = None
    verify_token: str | None = None
    app_secret: str | None = None
    phone_number_id: str | None = None

    @property
    def live(self) -> bool:
        return bool(self.token and self.phone_number_id)


def load_config(vault: Any | None) -> WhatsAppConfig:
    """Lee ``whatsapp-test-*`` del vault; sin vault cae al entorno."""
    def read(name: str, env: str) -> str | None:
        if vault is not None:
            try:
                value = vault.get(name)
            except Exception:
                value = None
            if value:
                return value
        return os.environ.get(env) or None

    return WhatsAppConfig(
        phone_number=read("whatsapp-test-phone", "WHATSAPP_TEST_PHONE"),
        token=read("whatsapp-test-token", "WHATSAPP_TEST_TOKEN"),
        verify_token=read("whatsapp-test-verify-token", "WHATSAPP_VERIFY_TOKEN"),
        app_secret=read("whatsapp-app-secret", "WHATSAPP_APP_SECRET"),
        phone_number_id=read("whatsapp-test-phone-id", "WHATSAPP_PHONE_NUMBER_ID"),
    )


class WhatsAppChannel:
    def __init__(
        self,
        broker: ApprovalBroker,
        *,
        config: WhatsAppConfig | None = None,
        vault: Any | None = None,
        http_client: Any | None = None,
    ) -> None:
        self.broker = broker
        self.config = config or load_config(vault)
        self._http = http_client
        self.outbox: list[dict[str, Any]] = []
        self._seen: dict[str, dict[str, Any]] = {}

    @property
    def simulator_mode(self) -> bool:
        return not self.config.live

    def verify_challenge(self, mode: str, token: str, challenge: str) -> str | None:
        expected = self.config.verify_token or "shield-demo-verify"
        if mode == "subscribe" and hmac.compare_digest(token, expected):
            return challenge
        return None

    def send_approval_request(self, approval_id: str, summary: str) -> dict[str, Any]:
        to = self.config.phone_number or "593990000000"
        payload = button_payload(to, approval_id, summary)
        if self.simulator_mode:
            self.outbox.append(payload)
            return {"simulated": True, "channel": "whatsapp-simulator", "payload": payload}
        url = f"{GRAPH_URL}/{self.config.phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {self.config.token}"}
        if self._http is not None:
            resp = self._http.post(url, json=payload, headers=headers)
            return {"simulated": False, "status_code": resp.status_code}
        import httpx

        resp = httpx.post(url, json=payload, headers=headers, timeout=10)
        return {"simulated": False, "status_code": resp.status_code}

    def send_text(self, text: str) -> dict[str, Any]:
        payload = {
            "messaging_product": "whatsapp",
            "to": self.config.phone_number or "593990000000",
            "type": "text",
            "text": {"body": text[:4096]},
        }
        self.outbox.append(payload)
        return {"simulated": self.simulator_mode, "payload": payload}

    def handle_payload(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Procesa mensajes; idempotente por ``message_id``."""
        results: list[dict[str, Any]] = []
        for msg in parse_webhook(payload):
            if not msg.message_id:
                results.append({"status": "ignored", "reason": "sin message_id"})
                continue
            if msg.message_id in self._seen:
                results.append(
                    {
                        **self._seen[msg.message_id],
                        "status": "duplicate",
                        "original_status": self._seen[msg.message_id].get("status"),
                        "message_id": msg.message_id,
                    }
                )
                continue
            result = self._handle_one(msg)
            self._seen[msg.message_id] = result
            results.append(result)
        return results

    def _handle_one(self, msg: WhatsAppMessage) -> dict[str, Any]:
        base = {"message_id": msg.message_id, "from": msg.from_number}
        if msg.kind != "button" or ":" not in msg.button_id:
            return {**base, "status": "ignored", "reason": "no es un botón de aprobación"}
        action, approval_id = msg.button_id.split(":", 1)
        req = self.broker.get(approval_id)
        if req is None:
            return {**base, "status": "not_found", "approval_id": approval_id}
        if action == "detail":
            steps = "; ".join(
                f"{s.get('action')} {s.get('target')}" for s in req.plan.get("steps") or []
            )
            self.send_text(f"Detalle {approval_id}: {req.plan.get('summary', '')}. Pasos: {steps}")
            return {**base, "status": "detail_sent", "approval_id": approval_id}
        if req.status != "pending":
            return {**base, "status": req.status, "approval_id": approval_id, "idempotent": True}
        if action == "approve":
            self.broker.approve(approval_id)
            self.send_text(f"Aprobado {approval_id}. Shield ejecuta el plan.")
            return {**base, "status": "approved", "approval_id": approval_id}
        if action == "reject":
            self.broker.reject(approval_id)
            self.send_text(f"Rechazado {approval_id}. No se ejecuta nada.")
            return {**base, "status": "rejected", "approval_id": approval_id}
        return {**base, "status": "ignored", "reason": f"acción desconocida: {action}"}


def create_router(channel: WhatsAppChannel) -> Any:
    """Router FastAPI: ``GET`` de verificación y ``POST`` firmado."""
    router = APIRouter()

    @router.get("/webhook/whatsapp")
    async def verify(request: Request) -> Any:
        params = request.query_params
        challenge = channel.verify_challenge(
            params.get("hub.mode", ""),
            params.get("hub.verify_token", ""),
            params.get("hub.challenge", ""),
        )
        if challenge is None:
            return PlainTextResponse("verification failed", status_code=403)
        return PlainTextResponse(challenge)

    @router.post("/webhook/whatsapp")
    async def receive(request: Request) -> Any:
        body = await request.body()
        secret = channel.config.app_secret
        if secret and not verify_signature(
            body, request.headers.get("x-hub-signature-256"), secret
        ):
            return PlainTextResponse("invalid signature", status_code=403)
        import json

        try:
            payload = json.loads(body or b"{}")
        except ValueError:
            return PlainTextResponse("invalid json", status_code=400)
        results = channel.handle_payload(payload)
        return {"status": "ok", "results": results, "simulator": channel.simulator_mode}

    return router


# Compatibilidad: el simulador también se usa sin montar el router.
__all__ = [
    "GRAPH_URL",
    "WhatsAppChannel",
    "WhatsAppConfig",
    "WhatsAppMessage",
    "button_payload",
    "create_router",
    "load_config",
    "parse_webhook",
    "simulated_click_payload",
    "verify_signature",
]
