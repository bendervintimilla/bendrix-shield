"""Aprobación por voz: Voice Transcribe → Spark → aprobación parcial.

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

_REJECT_WORDS = (
    "rechaza",
    "rechazo",
    "no apruebo",
    "cancela",
    "cancelar",
    "deten",
    "reject",
    "cancel",
    "deny",
    "stop",
)
_APPROVE_WORDS = (
    "si",
    "aprueba",
    "apruebo",
    "aprobado",
    "rota",
    "rotar",
    "adelante",
    "hazlo",
    "yes",
    "approve",
    "rotate",
)
_APPROVE_PHRASES = ("go ahead",)
_NEGATION_RE = re.compile(r"\b(?:no|nunca|never|do not|don't|dont)\b")


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


def _clean_target(raw: str) -> str:
    name = raw.strip().rstrip(".,")
    name = re.split(r"\s+(?:y|pero|por favor|and|please)\b", name)[0].strip()
    return name.rstrip(".,").strip()


def parse_voice_command(transcript: str) -> VoiceIntent:
    """Parser determinista (español e inglés) de la orden del dueño."""
    text = _normalize(transcript)
    intent = VoiceIntent(action="unknown", transcript=transcript)
    for match in re.finditer(r"\b(?:menos|excepto|salvo|except)\s+([a-z0-9 _-]+)", text):
        name = _clean_target(match.group(1))
        if name:
            intent.exclude_targets.append(name)
    for match in re.finditer(r"\bbut not\s+([a-z0-9 _-]+)", text):
        name = _clean_target(match.group(1))
        if name and name not in intent.exclude_targets:
            intent.exclude_targets.append(name)
    only = re.search(r"\b(?:solo|only)\s+([a-z0-9 _-]+)", text)
    if only and not intent.exclude_targets:
        name = _clean_target(only.group(1))
        if name:
            intent.only_targets.append(name)
    if any(word in text for word in _REJECT_WORDS):
        intent.action = "reject"
    elif _NEGATION_RE.search(text):
        intent.action = "unknown"
    elif any(re.search(rf"\b{re.escape(w)}\b", text) for w in _APPROVE_WORDS) or any(
        phrase in text for phrase in _APPROVE_PHRASES
    ):
        intent.action = "approve"
    return intent


def _target_matches(target: str, names: list[str]) -> bool:
    low = target.lower()
    return any(name and name.lower() in low for name in names)


def plan_preview(plan: dict[str, Any], intent: VoiceIntent) -> dict[str, Any]:
    """Calcula qué se rotaría con una intención parcial, sin aprobar nada."""
    targets: list[str] = []
    for step in plan.get("steps") or []:
        if not step.get("requires_approval", True):
            continue
        if step.get("action") not in (None, "rotate_token"):
            continue
        target = str(step.get("target", ""))
        if target and target not in targets:
            targets.append(target)
    excluded = list(intent.exclude_targets)
    if intent.only_targets:
        will_run = [t for t in targets if _target_matches(t, intent.only_targets)]
    else:
        will_run = [t for t in targets if not _target_matches(t, excluded)]
    unmatched = [name for name in excluded if not any(name.lower() in t.lower() for t in targets)]
    return {"will_run": will_run, "excluded": excluded, "unmatched": unmatched}


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


def interpret_checked(transcript: str, client: Any | None) -> tuple[VoiceIntent, Any | None]:
    """Corre Spark y el determinista; desacuerdo en aprobar -> unknown.

    Devuelve (intent, call_result|None). Sin Spark no aprueba a ciegas:
    si no hay cliente, el intent es unknown con source="no_spark".
    """
    deterministic = parse_voice_command(transcript)
    if client is None:
        return (
            VoiceIntent(action="unknown", transcript=transcript, source="no_spark"),
            None,
        )
    # Capturar CallResult si el cliente lo expone vía chat_completions.
    call_result: Any | None = None
    orig = client.chat_completions if hasattr(client, "chat_completions") else None

    def _capturing(*a: Any, **k: Any) -> Any:
        nonlocal call_result
        res = orig(*a, **k)  # type: ignore[misc]
        call_result = res
        return res

    # interpret_with_spark usa client.chat_completions; envolver temporalmente
    # solo si es un objeto mutable simple.
    spark_intent: VoiceIntent
    try:
        if orig is not None:
            try:
                client.chat_completions = _capturing  # type: ignore[attr-defined]
            except Exception:
                pass
        spark_intent = interpret_with_spark(transcript, client)
    finally:
        if orig is not None:
            try:
                client.chat_completions = orig  # type: ignore[attr-defined]
            except Exception:
                pass
    # Si Spark cayó al determinista (source deterministic), no hubo Spark real.
    if spark_intent.source != "spark":
        # interpret_with_spark devuelve deterministic ante NeedsCredits/error.
        # Sin aprobación de Spark no se aprueba a ciegas.
        if deterministic.action == "approve":
            return (
                VoiceIntent(
                    action="unknown",
                    exclude_targets=list(deterministic.exclude_targets),
                    only_targets=list(deterministic.only_targets),
                    transcript=transcript,
                    source="no_spark",
                ),
                call_result,
            )
        return deterministic, call_result
    if spark_intent.action == "approve" and deterministic.action != "approve":
        return (
            VoiceIntent(
                action="unknown",
                exclude_targets=list(spark_intent.exclude_targets),
                only_targets=list(spark_intent.only_targets),
                transcript=transcript,
                source="disagreement",
            ),
            call_result,
        )
    if spark_intent.action != deterministic.action and spark_intent.action == "approve":
        return (
            VoiceIntent(action="unknown", transcript=transcript, source="disagreement"),
            call_result,
        )
    # Acuerdo (o Spark no aprueba): se conserva el intent de Spark,
    # fusionando exclusiones del determinista si Spark aprobó igual.
    if spark_intent.action == "approve" and deterministic.action == "approve":
        merged_ex = list(
            dict.fromkeys([*spark_intent.exclude_targets, *deterministic.exclude_targets])
        )
        merged_only = spark_intent.only_targets or deterministic.only_targets
        return (
            VoiceIntent(
                action="approve",
                exclude_targets=merged_ex,
                only_targets=list(merged_only),
                transcript=transcript,
                source="spark",
            ),
            call_result,
        )
    return spark_intent, call_result


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

    def cancel(self, approval_id: str) -> dict[str, Any]:
        intent = self._awaiting.pop(approval_id, None)
        if intent is None:
            return {"status": "nothing_to_confirm", "approval_id": approval_id}
        return {
            "status": "cancelled",
            "approval_id": approval_id,
            "intent": intent.public(),
        }

    def awaiting_intent(self, approval_id: str) -> VoiceIntent | None:
        return self._awaiting.get(approval_id)

    def has_awaiting(self) -> bool:
        return bool(self._awaiting)

    def _apply(self, approval_id: str, intent: VoiceIntent, *, confirmed: bool) -> dict[str, Any]:
        base = {"approval_id": approval_id, "intent": intent.public()}
        req = self.broker.get(approval_id)
        if intent.is_partial and req is not None:
            base.update(plan_preview(req.plan, intent))
        if intent.action == "unknown":
            return {**base, "status": "unknown_command"}
        if intent.action == "reject":
            self.broker.reject(approval_id)
            return {**base, "status": "rejected"}
        if intent.is_partial and not confirmed:
            self._awaiting[approval_id] = intent
            return {**base, "status": "confirmation_required"}
        approved_req = self.broker.approve(
            approval_id,
            exclude_targets=intent.exclude_targets,
            only_targets=intent.only_targets or None,
        )
        return {**base, "status": "approved", "approved_steps": approved_req.approved_steps}


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
