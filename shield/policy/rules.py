"""Reglas YAML por agente y detección de campos sensibles por significado."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

POLICIES_DIR = Path(__file__).parent / "policies"

# Fragmentos que, dentro del nombre de un campo, lo vuelven sensible.
# No es una lista cerrada de nombres exactos: cualquier alias que contenga
# uno de estos conceptos (iban, cuenta, llave, pago, correo...) cae aquí.
_SENSITIVE_TOKENS = (
    "iban",
    "bank",
    "account",
    "cuenta",
    "key",
    "llave",
    "secret",
    "token",
    "password",
    "passwd",
    "credential",
    "payment",
    "pago",
    "payee",
    "beneficiary",
    "beneficiario",
    "email",
    "correo",
    "mail",
    "domain",
    "dominio",
    "routing",
    "swift",
    "bic",
    "card",
    "tarjeta",
)

_AMOUNT_KEYS = ("amount", "total", "monto", "price", "cost", "valor", "value", "importe")


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def is_sensitive_field(name: str, declared: list[str] | tuple[str, ...] = ()) -> bool:
    norm = _norm(name)
    declared_norm = {_norm(d) for d in declared}
    if norm in declared_norm:
        return True
    # Alias declarados también por inclusión (p. ej. supplier_email vs email).
    if any(d and (d in norm or norm in d) for d in declared_norm):
        return True
    return any(tok in norm for tok in (_norm(t) for t in _SENSITIVE_TOKENS))


def sensitive_fields_in(
    args: dict[str, Any], declared: list[str] | tuple[str, ...] = ()
) -> list[str]:
    found: list[str] = []

    def walk(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                walk(f"{prefix}.{k}" if prefix else str(k), v)
        else:
            key = prefix.rsplit(".", 1)[-1]
            if prefix and is_sensitive_field(key, declared):
                found.append(prefix)

    walk("", args)
    return found


def amount_in(args: dict[str, Any]) -> float | None:
    for key, value in args.items():
        if isinstance(value, dict):
            inner = amount_in(value)
            if inner is not None:
                return inner
        norm = _norm(key)
        if any(tok in norm for tok in _AMOUNT_KEYS) and isinstance(value, (int, float)):
            return float(value)
    return None


@dataclass
class ToolRule:
    name: str
    effect: str = "read"
    sensitive_fields: list[str] = field(default_factory=list)


@dataclass
class AgentPolicy:
    agent: str
    app: str = ""
    tools: dict[str, ToolRule] = field(default_factory=dict)
    sensitive_fields: list[str] = field(default_factory=list)
    ask_owner_if: list[str] = field(default_factory=list)
    limits: dict[str, Any] = field(default_factory=dict)

    @property
    def max_amount_usd(self) -> float | None:
        raw = self.limits.get("max_amount_usd")
        return float(raw) if raw is not None else None

    def asks(self, condition: str) -> bool:
        return condition in self.ask_owner_if


def load_policy(agent: str, policies_dir: Path | None = None) -> AgentPolicy | None:
    base = policies_dir or POLICIES_DIR
    for path in sorted(base.glob("*.yaml")) + sorted(base.glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if data.get("agent") != agent:
            continue
        tools = {
            t["name"]: ToolRule(
                name=t["name"],
                effect=str(t.get("effect", "read")),
                sensitive_fields=list(t.get("sensitive_fields") or []),
            )
            for t in (data.get("tools") or [])
        }
        return AgentPolicy(
            agent=agent,
            app=str(data.get("app", "")),
            tools=tools,
            sensitive_fields=list(data.get("sensitive_fields") or []),
            ask_owner_if=list(data.get("ask_owner_if") or []),
            limits=dict(data.get("limits") or {}),
        )
    return None


def load_all(policies_dir: Path | None = None) -> dict[str, AgentPolicy]:
    base = policies_dir or POLICIES_DIR
    out: dict[str, AgentPolicy] = {}
    for path in sorted(base.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        agent = data.get("agent")
        if agent:
            policy = load_policy(str(agent), base)
            if policy:
                out[policy.agent] = policy
    return out
