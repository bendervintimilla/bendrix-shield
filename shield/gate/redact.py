"""Redacción determinista de llaves y PII (sin LLM, solo regex).

Los hallazgos reportan solo el **tipo**, nunca el valor encontrado.
La redacción es idempotente: redactar dos veces da lo mismo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from shield.textnorm import decode_base64_segments, normalize

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}")),
    ("openai_key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{10,}")),
    ("google_key", re.compile(r"AIza[0-9A-Za-z_\-]{10,}")),
    ("llm_key", re.compile(r"LLM_[A-Za-z0-9_\-]{6,}")),
    ("github_token", re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{10,}")),
    ("github_pat", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("aws_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("shield_token", re.compile(r"shd_[A-Za-z0-9_\-]{6,}")),
    ("meta_key_env", re.compile(r"META_MODEL_API_KEY\s*=\s*\S+", re.IGNORECASE)),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
    ("bearer", re.compile(r"Bearer\s+[A-Za-z0-9._\-]{12,}", re.IGNORECASE)),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,3})?\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    # Teléfono internacional (+593…) o nacional largo con separadores.
    (
        "phone",
        re.compile(r"(?:\+\d{1,3}[ ]?)?(?:\(?\d{2,4}\)?[ ]?)?\d{3,4}[ \-]\d{4}\b|\+\d{10,15}\b"),
    ),
]


# Única excepción a los patrones: identificadores CVE (``CVE-2026-1234``), que
# el patrón de teléfono confundía. Se apartan antes de redactar y se reponen
# después; todo lo demás (``tel-0991 2345``, ``WA-+593…``, ids) sigue igual.
_CVE = re.compile(r"\bCVE-(?:19|20)\d{2}-\d{4,}\b")
_HOLD = "\ue000"


def _protect_cves(text: str) -> tuple[str, list[str]]:
    if _HOLD in text:
        return text, []
    held: list[str] = []

    def _keep(m: re.Match[str]) -> str:
        held.append(m.group(0))
        return f"{_HOLD}{len(held) - 1}{_HOLD}"

    return _CVE.sub(_keep, text), held


def _restore_cves(text: str, held: list[str]) -> str:
    for i, cve in enumerate(held):
        text = text.replace(f"{_HOLD}{i}{_HOLD}", cve)
    return text


@dataclass(frozen=True)
class Redaction:
    kind: str
    count: int


def _kind_in(text: str) -> str | None:
    text = _CVE.sub("", text)
    for kind, pattern in PATTERNS:
        if pattern.search(text):
            return kind
    return None


def redact_text(text: str) -> tuple[str, list[Redaction]]:
    findings: dict[str, int] = {}
    out, held = _protect_cves(text)
    for kind, pattern in PATTERNS:
        out, n = pattern.subn(f"[REDACTED:{kind}]", out)
        # La clave de OpenAI también la caza el patrón genérico tras redactar;
        # contar solo sustituciones reales evita dobles conteos.
        if n:
            findings[kind] = findings.get(kind, 0) + n
    # Después de los patrones en claro: un segmento base64 que decodifica a
    # una llave/token/PII se redacta entero (``<tipo>_b64``).
    for encoded, decoded in decode_base64_segments(out):
        kind = _kind_in(normalize(decoded))
        if kind is None or encoded not in out:
            continue
        label = f"{kind}_b64"
        n = out.count(encoded)
        out = out.replace(encoded, f"[REDACTED:{label}]")
        findings[label] = findings.get(label, 0) + n
    out = _restore_cves(out, held)
    return out, [Redaction(kind=k, count=v) for k, v in sorted(findings.items())]


def redact_payload(payload: object) -> tuple[object, list[Redaction]]:
    """Redacta recursivamente str/dict/list; el resto pasa igual."""
    totals: dict[str, int] = {}

    def walk(node: object) -> object:
        if isinstance(node, str):
            redacted, found = redact_text(node)
            for f in found:
                totals[f.kind] = totals.get(f.kind, 0) + f.count
            return redacted
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, tuple):
            return tuple(walk(v) for v in node)
        return node

    result = walk(payload)
    return result, [Redaction(kind=k, count=v) for k, v in sorted(totals.items())]
