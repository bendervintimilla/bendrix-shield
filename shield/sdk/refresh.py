"""Auto-recuperación del cliente si su token Shield rotó (H6.3).

``ShieldClient`` envuelve cualquier cliente estilo OpenAI: si una llamada
devuelve 401 (token rotado/revocado), refresca ``api_key`` desde el registro
local del agente y reintenta **una vez**. Sin cambio de código en la app.
"""

from __future__ import annotations

from typing import Any


def is_auth_error(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if status is None:
        resp = getattr(exc, "response", None)
        status = getattr(resp, "status_code", None)
    if status == 401:
        return True
    text = str(exc).lower()
    return "401" in text and ("rotated" in text or "revoked" in text or "invalid" in text)


def refresh_client_token(client: Any, store: Any, agent: str) -> bool:
    """Actualiza ``client.api_key`` desde el store si cambió. True si refrescó."""
    fresh = store.get_token(agent) if store is not None else None
    if fresh and getattr(client, "api_key", None) != fresh:
        client.api_key = fresh
        return True
    return False


class _AttrProxy:
    """Proxy recursivo: delega atributos y reintenta llamadas tras un 401."""

    def __init__(self, target: Any, root: ShieldClient) -> None:
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_root", root)

    def __getattr__(self, name: str) -> Any:
        target = object.__getattribute__(self, "_target")
        root = object.__getattribute__(self, "_root")
        value = getattr(target, name)
        if callable(value):

            def call(*args: Any, **kwargs: Any) -> Any:
                try:
                    return value(*args, **kwargs)
                except Exception as exc:
                    if is_auth_error(exc) and root._refresh():
                        return value(*args, **kwargs)
                    raise

            return call
        # Objetos con más atributos (chat, chat.completions…) se envuelven;
        # valores simples (str, URL…) pasan tal cual.
        if hasattr(value, "__dict__") or type(value).__module__ not in ("builtins",):
            return _AttrProxy(value, root)
        return value

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(object.__getattribute__(self, "_target"), name, value)


class ShieldClient:
    """Envuelve el cliente real; expone la misma superficie vía proxy."""

    def __init__(self, client: Any, store: Any, agent: str) -> None:
        object.__setattr__(self, "_client", client)
        object.__setattr__(self, "_store", store)
        object.__setattr__(self, "_agent", agent)

    @property
    def raw(self) -> Any:
        return object.__getattribute__(self, "_client")

    def _refresh(self) -> bool:
        return refresh_client_token(
            object.__getattribute__(self, "_client"),
            object.__getattribute__(self, "_store"),
            object.__getattribute__(self, "_agent"),
        )

    def refresh_now(self) -> bool:
        return self._refresh()

    def __getattr__(self, name: str) -> Any:
        client = object.__getattribute__(self, "_client")
        value = getattr(client, name)
        if callable(value) or (hasattr(value, "__dict__") or type(value).__module__ != "builtins"):
            return _AttrProxy(value, self) if not callable(value) else self._wrap_call(value)
        return value

    def _wrap_call(self, value: Any) -> Any:
        def call(*args: Any, **kwargs: Any) -> Any:
            try:
                return value(*args, **kwargs)
            except Exception as exc:
                if is_auth_error(exc) and self._refresh():
                    return value(*args, **kwargs)
                raise

        return call

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            setattr(object.__getattribute__(self, "_client"), name, value)
