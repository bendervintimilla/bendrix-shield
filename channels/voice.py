"""Aprobación por voz (H8): Voice Transcribe → Spark → aprobación parcial.

La nota de voz se transcribe con Muse Voice Transcribe vía
``shield.meta_client.MetaClient.transcribe_file`` (ruta documentada
``POST /v1/asr/transcribe``). La orden se interpreta con Spark 1.3 si hay
cliente y, sin créditos, con un parser determinista en español. Ejemplo:
«sí, rota todo menos Stripe» aprueba todos los pasos menos los cuyo
objetivo menciona Stripe. Toda aprobación parcial exige confirmación
explícita antes de ejecutar ningún paso.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from channels.approvals import ApprovalBroker, ChannelApprover

_REJECT_WORDS = ("rechaza", "rechazo", "no apruebo", "cancela", "cancelar", "deten")
_APPROVE_WORDS = ("si", "aprueba", "apruebo", "aprobado", "rota", "rotar", "adelante", "hazlo")


def _normalize(text: str) -> str:
    lowered = text.lower()
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


@dataclass
class VoiceIntent:
    action: str  # approve | reject | unknown
    exclude_targets: list[str] = field(default_factory=list)
    only_targets: list[str] = field(default_factory=list)
    transcript: str = ""
    source: str = "deterministic"  # deterministic | spark

    @property
    def is_partial(self) -> bool:
        return bool(self.exclude_targets or self.only_targets)

    def public(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "exclude_targets": list(self.exclude_targets),
            "only_targets": list(self.only_targets),
            "is_partial": self.is_partial,
            "source": self.source,
            "transcript": self.transcript,
        }


def parse_voice_command(transcript: str) -> VoiceIntent:
    """Parser determinista (español neutro) de la orden del dueño."""
    text = _normalize(transcript)
    intent = VoiceIntent(action="unknown", transcript=transcript)
    for match in re.finditer(r"\b(?:menos|excepto|salvo)\s+([a-z0-9 _-]+)", text):
        name = match.group(1).strip().rstrip(".,")
        # Cortar en conectores que ya no son parte del nombre.
        name = re.split(r"\s+(?:y|pero|por favor)\b", name)[0].strip()
        if name:
            intent.exclude_targets.append(name)
    only = re.search(r"\bsolo\s+([a-z0-9 _-]+)", text)
    if only and not intent.exclude_targets:
        name = re.split(r"\s+(?:y|pero|por favor)\b", only.group(1).strip().rstrip(".,"))[0].strip()
        if name:
            intent.only_targets.append(name)
    if any(word in text for word in _REJECT_WORDS):
        intent.action = "reject"
    elif any(re.search(rf"\b{re.escape(w)}\b", text) for w in _APPROVE_WORDS):
        intent.action = "approve"
    return intent


def interpret_with_spark(transcript: str, client: Any | None) -> VoiceIntent:
    """Spark 1.3 interpreta la orden; sin créditos cae al parser local."""
    if client is None:
        return parse_voice_command(transcript)
    from shield.meta_client import NeedsCredits

    try:
        result = client.chat_completions(
            model="muse-spark-1.3",
            messages=[
                {
                    "role": "system",
                    "content": "Extrae la decisión del dueño en JSON: "
                    '{"action":"approve|reject","exclude_targets":[],"only_targets":[]}.'
                    " «menos X»/«excepto X» va en exclude_targets; «solo X» en only_targets.",
                },
                {"role": "user", "content": transcript},
            ],
        )
        choices = result.data.get("choices") or []
        content = ((choices[0].get("message") or {}).get("content") or "") if choices else ""
        data = json.loads(content)
        return VoiceIntent(
            action=str(data.get("action", "unknown")),
            exclude_targets=[str(x) for x in data.get("exclude_targets") or []],
            only_targets=[str(x) for x in data.get("only_targets") or []],
            transcript=transcript,
            source="spark",
        )
    except (NeedsCredits, ValueError, TypeError, KeyError, IndexError):
        return parse_voice_command(transcript)


def transcribe_audio(wav_path: str | Path, client: Any | None) -> dict[str, Any]:
    """Transcribe con Voice Transcribe; sin créditos lo marca y no inventa texto."""
    from shield.meta_client import NeedsCredits

    if client is None:
        return {"status": "needs_credits", "transcript": "", "needs_credits": True}
    try:
        result = client.transcribe_file(wav_path)
    except NeedsCredits:
        return {"status": "needs_credits", "transcript": "", "needs_credits": True}
    transcript = str(result.data.get("transcript") or "")
    return {"status": "ok", "transcript": transcript, "needs_credits": False}


class VoiceApprovalFlow:
    """Aplica una orden de voz sobre una aprobación pendiente del broker."""

    def __init__(self, broker: ApprovalBroker, *, client: Any | None = None) -> None:
        self.broker = broker
        self.client = client
        self._awaiting: dict[str, VoiceIntent] = {}

    def handle_transcript(
        self, approval_id: str, transcript: str, *, confirmed: bool = False
    ) -> dict[str, Any]:
        intent = interpret_with_spark(transcript, self.client)
        return self._apply(approval_id, intent, confirmed=confirmed)

    def handle_audio(
        self, approval_id: str, wav_path: str | Path, *, confirmed: bool = False
    ) -> dict[str, Any]:
        heard = transcribe_audio(wav_path, self.client)
        if heard.get("needs_credits"):
            return {**heard, "approval_id": approval_id, "status": "needs_credits"}
        return self.handle_transcript(approval_id, heard["transcript"], confirmed=confirmed)

    def confirm(self, approval_id: str) -> dict[str, Any]:
        intent = self._awaiting.pop(approval_id, None)
        if intent is None:
            return {"status": "nothing_to_confirm", "approval_id": approval_id}
        return self._apply(approval_id, intent, confirmed=True)

    def _apply(self, approval_id: str, intent: VoiceIntent, *, confirmed: bool) -> dict[str, Any]:
        base = {"approval_id": approval_id, "intent": intent.public()}
        if intent.action == "unknown":
            return {**base, "status": "unknown_command"}
        if intent.action == "reject":
            self.broker.reject(approval_id)
            return {**base, "status": "rejected"}
        if intent.is_partial and not confirmed:
            self._awaiting[approval_id] = intent
            return {**base, "status": "confirmation_required"}
        req = self.broker.approve(
            approval_id,
            exclude_targets=intent.exclude_targets,
            only_targets=intent.only_targets or None,
        )
        return {**base, "status": "approved", "approved_steps": req.approved_steps}


class VoiceApprover(ChannelApprover):
    """``Approver`` síncrono: la nota de voz ya trae la decisión.

    Si la orden es parcial y no viene confirmada, ``ask_owner`` no
    aprueba nada: deja la intención en ``pending_intent`` y el flujo se
    retoma con :meth:`confirm_and_resume_id`.
    """

    def __init__(
        self,
        broker: ApprovalBroker,
        transcript: str,
        *,
        client: Any | None = None,
        confirmed: bool = False,
    ) -> None:
        super().__init__(broker)
        self.transcript = transcript
        self.client = client
        self.confirmed = confirmed
        self.pending_intent: VoiceIntent | None = None
        self._flow = VoiceApprovalFlow(broker, client=client)

    def ask_owner(self, plan: Any) -> str | None:
        plan_dict = plan.to_dict() if hasattr(plan, "to_dict") else dict(plan)
        req = self.broker.request(plan_dict)
        self.pending_approval_id = req.approval_id
        self.asked.append(plan)
        intent = interpret_with_spark(self.transcript, self.client)
        if intent.action == "reject":
            self.broker.reject(req.approval_id)
            return None
        if intent.action == "unknown":
            return None
        if intent.is_partial and not self.confirmed:
            self.pending_intent = intent
            self._flow._awaiting[req.approval_id] = intent
            return None
        self.broker.approve(
            req.approval_id,
            exclude_targets=intent.exclude_targets,
            only_targets=intent.only_targets or None,
        )
        return req.approval_id

    def confirm_pending(self) -> str | None:
        """Confirma la aprobación parcial y devuelve el approval_id."""
        if self.pending_approval_id is None or self.pending_intent is None:
            return None
        outcome = self._flow.confirm(self.pending_approval_id)
        if outcome.get("status") != "approved":
            return None
        approval_id = self.pending_approval_id
        self.pending_intent = None
        return approval_id
