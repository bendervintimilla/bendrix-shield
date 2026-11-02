"""Canal WhatsApp: webhook verificado, botones y simulador.

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
import re
import subprocess
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from channels.approvals import ApprovalBroker

GRAPH_URL = "https://graph.facebook.com/v21.0"
MAX_MEDIA_BYTES = 5 * 1024 * 1024
_ALLOWED_MEDIA_SUFFIXES = (".whatsapp.net", ".fbcdn.net")
_ALLOWED_MEDIA_HOSTS = {"lookaside.fbsbx.com", "whatsapp.net", "fbcdn.net"}


def _local_or_sandbox() -> bool:
    if os.environ.get("SHIELD_SANDBOX") == "1":
        return True
    return os.environ.get("DEMO", "replay") in ("replay", "sandbox", "local")


def verify_signature(body: bytes, signature: str | None, app_secret: str) -> bool:
    if not signature or not app_secret:
        return False
    expected = "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", str(value or ""))


def numbers_match(a: str | None, b: str | None) -> bool:
    da, db = _digits(a), _digits(b)
    return bool(da and db and da == db)


def is_allowed_media_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        return False
    return host in _ALLOWED_MEDIA_HOSTS or host.endswith(_ALLOWED_MEDIA_SUFFIXES)


def convert_audio_to_wav(data: bytes, *, timeout: float = 30.0) -> bytes:
    """Convierte OGG/Opus a WAV 16 kHz mono con ffmpeg (sin shell)."""
    if len(data) > MAX_MEDIA_BYTES:
        raise ValueError("media too large: over 5 MB")
    with tempfile.TemporaryDirectory(prefix="wa-voice-") as tmp:
        src = Path(tmp) / "nota.ogg"
        dst = Path(tmp) / "nota.wav"
        src.write_bytes(data)
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(src),
                "-ar",
                "16000",
                "-ac",
                "1",
                "-f",
                "wav",
                str(dst),
            ],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0 or not dst.exists():
            detail = (proc.stderr or b"").decode(errors="replace")[-300:]
            raise ValueError(f"ffmpeg could not convert audio: {detail}")
        return dst.read_bytes()


def _http_get(http_client: Any, url: str, headers: dict[str, str]) -> Any:
    if http_client is not None and hasattr(http_client, "get"):
        return http_client.get(url, headers=headers)
    import httpx

    return httpx.get(url, headers=headers, timeout=30)


def download_media(media_id: str, config: WhatsAppConfig, http_client: Any = None) -> bytes:
    """Descarga media de Graph API validando dominio de Meta y tamaño."""
    if not config.token:
        raise ValueError("whatsapp token missing")
    headers = {"Authorization": f"Bearer {config.token}"}
    meta = _http_get(http_client, f"{GRAPH_URL}/{media_id}", headers)
    if int(getattr(meta, "status_code", 200) or 200) >= 400:
        raise ValueError(f"graph media lookup failed: {meta.status_code}")
    data = meta.json() if hasattr(meta, "json") else {}
    url = str((data or {}).get("url") or "")
    if not is_allowed_media_url(url):
        raise ValueError(f"media url host not allowed: {urlparse(url).hostname or url}")
    resp = _http_get(http_client, url, headers)
    if int(getattr(resp, "status_code", 200) or 200) >= 400:
        raise ValueError(f"graph media download failed: {resp.status_code}")
    content = bytes(getattr(resp, "content", b"") or b"")
    if len(content) > MAX_MEDIA_BYTES:
        raise ValueError("media too large: over 5 MB")
    return content


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
                elif raw.get("type") in ("audio", "voice") or raw.get("audio") or raw.get("voice"):
                    msg.kind = "audio"
                    media = raw.get("audio") or raw.get("voice") or {}
                    msg.audio_id = str(media.get("id", "") if isinstance(media, dict) else "")
                else:
                    msg.kind = "text"
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
        live_chain_getter: Callable[[], Any] | None = None,
        audio_converter: Callable[[bytes], bytes] | None = None,
    ) -> None:
        self.broker = broker
        self.config = config or load_config(vault)
        self._http = http_client
        self.outbox: list[dict[str, Any]] = []
        self._seen: dict[str, dict[str, Any]] = {}
        self.live_chain_getter = live_chain_getter
        self._audio_converter = audio_converter or convert_audio_to_wav
        self._inflight: set[str] = set()
        self._state_lock = threading.Lock()
        self._live_lock = threading.Lock()
        self._bg_threads: list[threading.Thread] = []

    @property
    def simulator_mode(self) -> bool:
        return not self.config.live

    def verify_challenge(self, mode: str, token: str, challenge: str) -> str | None:
        expected = self.config.verify_token or (
            "shield-demo-verify" if _local_or_sandbox() else None
        )
        if not expected:
            return None
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

    def send_text(self, text: str, to: str | None = None) -> dict[str, Any]:
        payload = {
            "messaging_product": "whatsapp",
            "to": to or self.config.phone_number or "593990000000",
            "type": "text",
            "text": {"body": text[:4096]},
        }
        self.outbox.append(payload)
        if self.simulator_mode:
            return {"simulated": True, "payload": payload}
        url = f"{GRAPH_URL}/{self.config.phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {self.config.token}"}
        if self._http is not None:
            resp = self._http.post(url, json=payload, headers=headers)
            return {"simulated": False, "status_code": resp.status_code, "payload": payload}
        import httpx

        resp = httpx.post(url, json=payload, headers=headers, timeout=10)
        return {"simulated": False, "status_code": resp.status_code, "payload": payload}

    def get_live_chain(self) -> Any:
        if self.live_chain_getter is None:
            return None
        try:
            return self.live_chain_getter()
        except Exception:
            return None

    def notify_guardian_plan(
        self, plan: dict[str, Any], approval_id: str | None = None
    ) -> dict[str, Any]:
        """Avisa al dueño del plan del guardián y pide la nota de voz."""
        summary = str(plan.get("summary") or "Containment plan")[:500]
        steps = "; ".join(
            f"{s.get('action')} {s.get('target')}".strip()
            for s in (plan.get("steps") or [])
            if isinstance(s, dict)
        )
        text = f"Shield plan: {summary}"
        if steps:
            text += f" Steps: {steps}."
        text += " Reply with a voice note: “yes, rotate it” / “no”."
        result = self.send_text(text[:1024])
        return {**result, "approval_id": approval_id, "text": text[:1024]}

    # Alias corto usado por el panel live.
    send_plan_to_owner = notify_guardian_plan

    def _contain_reply(self, contain: dict[str, Any]) -> str:
        attacker = (contain.get("attacker_after") or [None])[0]
        sdk = contain.get("sdk_statuses") or []
        sdk_text = " → ".join(str(s) for s in sdk) if sdk else "n/a"
        seconds = contain.get("contained_in_s", contain.get("time_to_first_401_s"))
        sec_text = f"{seconds}s" if seconds is not None else "n/a"
        if contain.get("status") == "ok":
            return (
                f"Containment done. Attacker: {attacker}. "
                f"SDK: {sdk_text}. Contained in {sec_text}."
            )
        return f"Containment result: {contain.get('status')} ({contain.get('error') or ''})."

    def _handle_live_message(self, msg: WhatsAppMessage) -> dict[str, Any] | None:
        chain = self.get_live_chain()
        if chain is None:
            return None
        is_confirm = msg.kind == "text" and msg.text.strip().lower().rstrip(".!") == "confirm"
        if msg.kind not in ("audio", "text") or (msg.kind == "text" and not is_confirm):
            return None
        base = {"message_id": msg.message_id, "from": msg.from_number, "channel": "whatsapp"}
        if not numbers_match(msg.from_number, self.config.phone_number):
            return {**base, "status": "ignored", "reason": "not_owner"}
        with self._live_lock:
            if msg.kind == "text":
                confirm = chain.step_voice_confirm
                try:
                    outcome = confirm(channel="whatsapp")  # type: ignore[call-arg]
                except TypeError:
                    outcome = confirm()
                status = str(outcome.get("status") or "")
                if status == "approved":
                    contain = chain.step_contain()
                    self.send_text(self._contain_reply(contain))
                    return {
                        **base,
                        "status": "approved",
                        "voice": outcome,
                        "contain": contain,
                    }
                self.send_text(f"Nothing to confirm (status: {status or 'unknown'}).")
                return {**base, "status": status or "ignored", "voice": outcome}
            # audio / voice
            if not msg.audio_id:
                return {**base, "status": "ignored", "reason": "sin audio_id"}
            if not getattr(chain, "_approval_id", None):
                return {**base, "status": "ignored", "reason": "no pending approval"}
            try:
                raw = download_media(msg.audio_id, self.config, self._http)
                wav = self._audio_converter(raw)
                voice = chain.step_voice(wav_bytes=wav, channel="whatsapp")
            except Exception as exc:
                return {**base, "status": "error", "error": str(exc)}
            transcript = str(voice.get("transcript") or "")
            intent = voice.get("intent") or {}
            action = str(intent.get("action") or voice.get("status") or "")
            heard = f"Heard: “{transcript}”. Understood: {action}."
            status = str(voice.get("status") or "")
            if status == "confirmation_required":
                self.send_text(heard + " Reply “confirm” to confirm.")
                return {**base, "status": status, "voice": voice}
            if status == "approved":
                contain = chain.step_contain()
                self.send_text(heard + " " + self._contain_reply(contain))
                return {**base, "status": "approved", "voice": voice, "contain": contain}
            self.send_text(heard + f" Status: {status}.")
            return {**base, "status": status or "ignored", "voice": voice}

    def has_live_work(self, payload: dict[str, Any]) -> bool:
        if self.get_live_chain() is None:
            return False
        for msg in parse_webhook(payload):
            if msg.kind == "audio":
                return True
            if msg.kind == "text" and msg.text.strip().lower().rstrip(".!") == "confirm":
                return True
        return False

    def handle_payload_background(self, payload: dict[str, Any]) -> threading.Thread:
        thread = threading.Thread(
            target=self.handle_payload, args=(payload,), daemon=True, name="whatsapp-live"
        )
        with self._state_lock:
            self._bg_threads.append(thread)
        thread.start()
        return thread

    def wait_for_background(self, timeout: float | None = None) -> None:
        with self._state_lock:
            threads = list(self._bg_threads)
        for thread in threads:
            thread.join(timeout=timeout)

    def handle_payload(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Procesa mensajes; idempotente por ``message_id``."""
        results: list[dict[str, Any]] = []
        for msg in parse_webhook(payload):
            if not msg.message_id:
                results.append({"status": "ignored", "reason": "sin message_id"})
                continue
            with self._state_lock:
                if msg.message_id in self._seen:
                    seen = self._seen[msg.message_id]
                    results.append(
                        {
                            **seen,
                            "status": "duplicate",
                            "original_status": seen.get("status"),
                            "message_id": msg.message_id,
                        }
                    )
                    continue
                if msg.message_id in self._inflight:
                    results.append(
                        {"status": "duplicate", "message_id": msg.message_id}
                    )
                    continue
                self._inflight.add(msg.message_id)
            try:
                result = self._handle_one(msg)
            finally:
                with self._state_lock:
                    self._inflight.discard(msg.message_id)
            with self._state_lock:
                self._seen[msg.message_id] = result
            results.append(result)
        return results

    def _handle_one(self, msg: WhatsAppMessage) -> dict[str, Any]:
        live = self._handle_live_message(msg)
        if live is not None:
            return live
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
        # En live (o con credenciales reales) la firma es obligatoria.
        if not secret and (os.environ.get("DEMO") == "live" or channel.config.live):
            return PlainTextResponse("app secret required", status_code=403)
        if not secret and not _local_or_sandbox():
            return PlainTextResponse("app secret required", status_code=403)
        if secret and not verify_signature(
            body, request.headers.get("x-hub-signature-256"), secret
        ):
            return PlainTextResponse("invalid signature", status_code=403)
        import json

        try:
            payload = json.loads(body or b"{}")
        except ValueError:
            return PlainTextResponse("invalid json", status_code=400)
        if channel.has_live_work(payload):
            channel.handle_payload_background(payload)
            return {
                "status": "ok",
                "results": [{"status": "queued", "channel": "whatsapp"}],
                "simulator": channel.simulator_mode,
            }
        results = channel.handle_payload(payload)
        return {"status": "ok", "results": results, "simulator": channel.simulator_mode}

    return router


# Compatibilidad: el simulador también se usa sin montar el router.
__all__ = [
    "GRAPH_URL",
    "MAX_MEDIA_BYTES",
    "WhatsAppChannel",
    "WhatsAppConfig",
    "WhatsAppMessage",
    "button_payload",
    "convert_audio_to_wav",
    "create_router",
    "download_media",
    "is_allowed_media_url",
    "load_config",
    "numbers_match",
    "parse_webhook",
    "simulated_click_payload",
    "verify_signature",
]
