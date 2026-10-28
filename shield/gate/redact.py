"""Redacción determinista de llaves y PII (sin LLM, solo regex).

Los hallazgos reportan solo el **tipo**, nunca el valor encontrado.
La redacción es idempotente: redactar dos veces da lo mismo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

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


@dataclass(frozen=True)
class Redaction:
    kind: str
    count: int


def redact_text(text: str) -> tuple[str, list[Redaction]]:
    findings: dict[str, int] = {}
    out = text
    for kind, pattern in PATTERNS:
        out, n = pattern.subn(f"[REDACTED:{kind}]", out)
        # La clave de OpenAI también la caza el patrón genérico tras redactar;
        # contar solo sustituciones reales evita dobles conteos.
        if n:
            findings[kind] = findings.get(kind, 0) + n
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
