"""Borradores de notificación de incidente: RGPD art. 33 y LOPDP (H5).

Siempre un borrador para revisión humana: nunca se envía solo y el texto
lo dice en la primera línea. Sin datos inventados: lo que no se conoce
queda como [completar] para quien revisa.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from shield.anomaly import AnomalyFinding
from shield.schemas import Exposure

DRAFT_MARK = (
    "BORRADOR — lo revisa un humano antes de cualquier envío. No es una notificación presentada."
)


@dataclass
class NoticeDraft:
    regime: str  # rgpd | lopdp
    title: str
    body: str

    def render(self) -> str:
        return f"# {self.title}\n\n{DRAFT_MARK}\n\n{self.body}"


def _facts(
    exposures: list[Exposure],
    anomalies: list[AnomalyFinding],
    summary: str,
) -> str:
    lines = [f"Resumen del incidente: {summary or '[completar]'}", ""]
    if exposures:
        lines.append("Exposiciones confirmadas/candidatas:")
        lines += [
            f"- {e.threat_id} sobre {e.asset_id}: {e.reason} (confianza {e.confidence})"
            for e in exposures
        ]
        lines.append("")
    if anomalies:
        lines.append("Anomalías detectadas:")
        lines += [f"- [{a.severity}] {a.agent}: {a.detail} (n={a.count})" for a in anomalies]
        lines.append("")
    return "\n".join(lines)


def draft_notice(
    *,
    summary: str,
    exposures: list[Exposure] | None = None,
    anomalies: list[AnomalyFinding] | None = None,
    regime: str = "rgpd",
    controller: str = "[completar: responsable del tratamiento]",
    detected_at: datetime | None = None,
) -> NoticeDraft:
    """Borrador con los campos que pide el régimen elegido."""
    exposures = exposures or []
    anomalies = anomalies or []
    when = (detected_at or datetime.now(UTC)).isoformat()
    facts = _facts(exposures, anomalies, summary)
    if regime == "lopdp":
        body = (
            f"Autoridad: Superintendencia de Protección de Datos Personales (Ecuador)\n"
            f"Responsable del tratamiento: {controller}\n"
            f"Fecha y hora de detección: {when}\n\n"
            "Notificación de vulneración de datos personales conforme a la Ley Orgánica "
            "de Protección de Datos Personales (LOPDP): se notifica a la autoridad y, si "
            "hay riesgo para las personas, también a las personas afectadas, con la "
            "descripción del incidente, las medidas adoptadas y las recomendaciones.\n\n"
            f"{facts}"
            "Categorías de datos posiblemente afectadas: [completar]\n"
            "Número aproximado de personas afectadas: [completar]\n"
            "Medidas adoptadas: [completar: contención, rotación/revocación, verificación]\n"
            "Medidas para mitigar efectos adversos: [completar]\n"
            "Punto de contacto: [completar]\n"
        )
        return NoticeDraft(regime="lopdp", title="Borrador de notificación LOPDP", body=body)
    body = (
        f"Autoridad de control: [completar]\n"
        f"Responsable del tratamiento (art. 33 RGPD): {controller}\n"
        f"Fecha y hora de conocimiento: {when}\n"
        "Plazo: sin dilación indebida y, de ser posible, dentro de las 72 horas desde "
        "el conocimiento (art. 33.1 RGPD); si se supera, se motiva el retraso.\n\n"
        f"{facts}"
        "Categorías y número aproximado de personas y registros afectados: [completar]\n"
        "Probables consecuencias de la violación: [completar]\n"
        "Medidas adoptadas o propuestas (art. 33.3.d): [completar: contención, "
        "rotación/revocación de credenciales, verificación]\n"
        "Nombre y contacto del DPD o punto de contacto: [completar]\n"
    )
    return NoticeDraft(regime="rgpd", title="Borrador de notificación RGPD art. 33", body=body)


def draft_both(**kwargs: object) -> list[NoticeDraft]:
    return [draft_notice(regime="rgpd", **kwargs), draft_notice(regime="lopdp", **kwargs)]  # type: ignore[arg-type]
