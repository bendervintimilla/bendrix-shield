"""Detección de inyección: el contenido externo es dato, nunca instrucción."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from shield.policy.extract import ExtractedDoc, Segment, VisionFn, extract_any

_STRONG: list[tuple[str, re.Pattern[str]]] = [
    (
        "ignore_instructions",
        re.compile(
            r"ignora?\s+(tus|las|todas|previous|prior).{0,30}instrucciones|ignore\s+(your|all|previous|prior)\s+instructions|disregard\s+(your|the)\s+instructions",  # noqa: E501
            re.I,
        ),
    ),
    (
        "change_sensitive",
        re.compile(
            r"(cambia|actualiza|modifica|change|update|set|replace).{0,40}(iban|cuenta|account|bank|dominio de pago|payment|correo|email|llave|api\s*key|beneficiario)",  # noqa: E501
            re.I,
        ),
    ),
    (
        "reveal_secret",
        re.compile(
            r"(imprime|imprimir|muestra|mostrar|revela|revelar|env[ií]a|enviar|manda|mandar|print|reveal|show|send|leak|disclose|share|include|provide|output|paste|expose|divulge|forward|incluye|incluir|incluy\w*|comparte|compartir|divulga|divulgar|expone|exponer|entrega|entregar|proporciona|proporcionar|facilita|facilitar|copia|copiar|adjunta|reenv[ií]a|give|tell|dime|dame|pass|inclua|compartilhe|compartilhar|revele|mostre|envie|divulgue|exponha|forne[çc]a|encaminhe).{0,50}(api[\s_-]?key|credentials?|credencial(?:es)?|chaves?|llaves?|claves?|keys?|secrets?|secretos?|segredos?|tokens?|passwords?|contrase[ñn]as?|senhas?|system\s*prompt|prompt del sistema|private\s*key|llave privada|chave privada|access\s*token|auth\s*token)",  # noqa: E501
            re.I,
        ),
    ),
    (
        "reveal_secret_rev",
        re.compile(
            r"(api[\s_-]?key|credentials?|credencial(?:es)?|chaves?|llaves?|claves?|secrets?|secretos?|segredos?|tokens?|system\s*prompt|prompt del sistema).{0,50}(incluye|incluir|incluy\w*|comparte|revela|muestra|env[ií]a|manda|divulga|expone|entrega|proporciona|copia|reenv[ií]a|include|reveal|show|send|leak|disclose|share|provide|output|paste|expose|inclua|compartilhe|revele|mostre|envie|divulgue|exponha|forne[çc]a|respuesta|response|resposta|reply)",  # noqa: E501
            re.I,
        ),
    ),
    (
        "system_prompt",
        re.compile(
            r"system\s*prompt|prompt del sistema|eres ahora|you are now|act[uú]a como|act as|new instructions|nuevas instrucciones",  # noqa: E501
            re.I,
        ),
    ),
    (
        "transfer_directive",
        re.compile(
            r"(transfiere|transfer|wire|paga|pay).{0,50}(a esta cuenta|to this account|nueva cuenta|new account|inmediatamente|immediately)",  # noqa: E501
            re.I,
        ),
    ),
    (
        "override_policy",
        re.compile(
            r"(sin (pedir|preguntar)|don'?t (ask|tell)|no (le )?digas|secretly|en secreto|bypass|omite la (pol[ií]tica|aprobaci[oó]n)|skip approval)",  # noqa: E501
            re.I,
        ),
    ),
]

_WEAK: list[tuple[str, re.Pattern[str]]] = [
    (
        "urgency",
        re.compile(r"\b(urgente|urgent|inmediatamente|immediately|ahora mismo|right now)\b", re.I),
    ),
    (
        "imperative_agent",
        re.compile(r"\b(ejecuta|execute|run|haz esto|do this|obedece|obey|debes|you must)\b", re.I),
    ),
    ("secrecy", re.compile(r"\b(confidencial|confidential|no compartas|do not share)\b", re.I)),
]


@dataclass
class InjectionHit:
    kind: str
    fragment: str
    location: str
    doc_id: str
    strength: str = "strong"  # strong | weak

    def evidence(self) -> str:
        frag = " ".join(self.fragment.split())[:160]
        return f"{self.doc_id}:{self.location}:{self.kind}: {frag!r}"


@dataclass
class ScanResult:
    hits: list[InjectionHit] = field(default_factory=list)

    @property
    def strong(self) -> list[InjectionHit]:
        return [h for h in self.hits if h.strength == "strong"]

    @property
    def weak(self) -> list[InjectionHit]:
        return [h for h in self.hits if h.strength == "weak"]

    @property
    def suspicious(self) -> bool:
        return len(self.weak) >= 2


@dataclass
class UntrustedDoc:
    """Contenido externo marcado como dato no confiable."""

    doc_id: str
    extracted: ExtractedDoc
    origin: str = "external"

    @property
    def text(self) -> str:
        return self.extracted.text

    @property
    def segments(self) -> list[Segment]:
        return self.extracted.segments


def untrusted(
    doc: Any, doc_id: str = "doc", *, origin: str = "external", vision_fn: VisionFn | None = None
) -> UntrustedDoc:
    """Marca contenido externo (factura, aviso, audio transcrito, imagen)."""
    if isinstance(doc, UntrustedDoc):
        return doc
    extracted = extract_any(doc, doc_id=doc_id, vision_fn=vision_fn)
    return UntrustedDoc(doc_id=doc_id, extracted=extracted, origin=origin)


def _segments_of(source: Any) -> tuple[str, list[Segment]]:
    if isinstance(source, UntrustedDoc):
        return source.doc_id, source.segments
    if isinstance(source, ExtractedDoc):
        return source.doc_id, source.segments
    if isinstance(source, dict) and "doc_id" in source:
        sub = extract_any(source, doc_id=str(source.get("doc_id")))
        return sub.doc_id, sub.segments
    if isinstance(source, str):
        return "inline", [Segment("body", source)]
    extracted = extract_any(source)
    return extracted.doc_id, extracted.segments


def scan_source(source: Any) -> ScanResult:
    doc_id, segments = _segments_of(source)
    result = ScanResult()
    for seg in segments:
        for kind, pattern in _STRONG:
            m = pattern.search(seg.text)
            if m:
                start = max(m.start() - 40, 0)
                result.hits.append(
                    InjectionHit(
                        kind, seg.text[start : m.end() + 40], seg.location, doc_id, "strong"
                    )
                )
        for kind, pattern in _WEAK:
            m = pattern.search(seg.text)
            if m:
                result.hits.append(InjectionHit(kind, m.group(0), seg.location, doc_id, "weak"))
    return result


def scan_sources(sources: list[Any] | tuple[Any, ...] | None) -> ScanResult:
    merged = ScanResult()
    for source in sources or []:
        merged.hits.extend(scan_source(source).hits)
    return merged
