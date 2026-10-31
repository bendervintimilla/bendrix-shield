"""Decorador @shield.tool: toda herramienta con efecto pasa por policy.check."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any

from shield.policy.check import PolicyEngine
from shield.policy.injection import UntrustedDoc
from shield.schemas import Decision
from shield.sdk.pending import PendingRegistry, PolicyBlocked, PolicyPending, default_registry


def _collect_sources(args: dict[str, Any], explicit: Any) -> list[Any]:
    sources: list[Any] = list(explicit or [])
    for value in args.values():
        if isinstance(value, UntrustedDoc):
            sources.append(value)
        elif isinstance(value, (list, tuple)):
            sources.extend(v for v in value if isinstance(v, UntrustedDoc))
    # No duplicar por identidad.
    seen: set[int] = set()
    unique: list[Any] = []
    for item in sources:
        if id(item) not in seen:
            seen.add(id(item))
            unique.append(item)
    return unique


def _public_args(args: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in args.items() if not isinstance(v, UntrustedDoc) and k != "_sources"}


def tool(
    *,
    effect: str = "read",
    agent: str = "default",
    name: str | None = None,
    engine: PolicyEngine | None = None,
    registry: PendingRegistry | None = None,
) -> Callable[..., Any]:
    """Envuelve una función: check antes de ejecutar.

    allow -> ejecuta; block -> PolicyBlocked; ask_owner -> PolicyPending
    con ``pending_id`` registrado para que el canal lo apruebe.
    """
    active_engine = engine or PolicyEngine()
    active_registry = registry or default_registry

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        tool_name = name or fn.__name__
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*f_args: Any, **f_kwargs: Any) -> Any:
            bound = sig.bind_partial(*f_args, **f_kwargs)
            bound.apply_defaults()
            call_args = dict(bound.arguments)
            explicit_sources = call_args.pop("_sources", None)
            sources = _collect_sources(call_args, explicit_sources)
            check_args = _public_args(call_args)
            # Los documentos aportan su id como rastro, no su texto como arg.
            if sources:
                check_args.setdefault(
                    "source_doc_ids", [getattr(s, "doc_id", "inline") for s in sources]
                )
            decision = active_engine.check(agent, tool_name, check_args, sources, effect=effect)
            if decision.decision is Decision.BLOCK:
                raise PolicyBlocked(decision)
            if decision.decision is Decision.ASK_OWNER:
                pending = active_registry.add(
                    agent=agent,
                    tool=tool_name,
                    args=check_args,
                    decision=decision,
                    fn=fn,
                )
                raise PolicyPending(pending)
            return fn(*f_args, **f_kwargs)

        wrapper.__shield_tool__ = {  # type: ignore[attr-defined]
            "agent": agent,
            "tool": tool_name,
            "effect": effect,
        }
        return wrapper

    return decorator
