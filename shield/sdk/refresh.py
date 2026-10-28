"""Auto-recuperación del cliente si su token Shield rotó (H6.3).

``ShieldClient`` envuelve cualquier cliente estilo OpenAI: si una llamada
devuelve 401 (token rotado/revocado), refresca ``api_key`` desde el registro
local del agente y reintenta **una vez**. Sin cambio de código en la app.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

IdentityFetcher = Callable[[], str | None]


def expected_service_account() -> str | None:
    """Cuenta de servicio exigida al refresh, si el despliegue la fija."""
    return os.environ.get("SHIELD_EXPECTED_SERVICE_ACCOUNT") or None


def fetch_service_account_email() -> str | None:
    """Email de la identidad del servicio (metadata de Cloud Run/GCE)."""
    try:
        import httpx

        resp = httpx.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/"
            "service-accounts/default/email",
            headers={"Metadata-Flavor": "Google"},
            timeout=1.0,
        )
        if resp.status_code == 200:
            return resp.text.strip() or None
    except Exception:
        return None
    return None


def refresh_allowed(
    *,
    expected: str | None = None,
    fetcher: IdentityFetcher | None = None,
) -> bool:
    """Sin identidad exigida, el refresh local sigue como en H6.

    Con ``SHIELD_EXPECTED_SERVICE_ACCOUNT`` fijada, el refresh solo
    procede si la identidad del servicio coincide; si no se puede
    comprobar, falla cerrado (no refresca).
    """
    wanted = expected if expected is not None else expected_service_account()
    if not wanted:
        return True
    actual = (fetcher or fetch_service_account_email)()
    return actual == wanted


def is_auth_error(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if status is None:
        resp = getattr(exc, "response", None)
        status = getattr(resp, "status_code", None)
    if status == 401:
        return True
    text = str(exc).lower()
    return "401" in text and ("rotated" in text or "revoked" in text or "invalid" in text)


def refresh_client_token(
    client: Any,
    store: Any,
    agent: str,
    *,
    expected_service_account: str | None = None,
    identity_fetcher: IdentityFetcher | None = None,
) -> bool:
    """Actualiza ``client.api_key`` desde el store si cambió. True si refrescó."""
    if not refresh_allowed(expected=expected_service_account, fetcher=identity_fetcher):
        return False
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

    def __init__(
        self,
        client: Any,
        store: Any,
        agent: str,
        *,
        expected_service_account: str | None = None,
        identity_fetcher: IdentityFetcher | None = None,
    ) -> None:
        object.__setattr__(self, "_client", client)
        object.__setattr__(self, "_store", store)
        object.__setattr__(self, "_agent", agent)
        object.__setattr__(self, "_expected_sa", expected_service_account)
        object.__setattr__(self, "_identity_fetcher", identity_fetcher)

    @property
    def raw(self) -> Any:
        return object.__getattribute__(self, "_client")

    def _refresh(self) -> bool:
        return refresh_client_token(
            object.__getattribute__(self, "_client"),
            object.__getattribute__(self, "_store"),
            object.__getattribute__(self, "_agent"),
            expected_service_account=object.__getattribute__(self, "_expected_sa"),
            identity_fetcher=object.__getattribute__(self, "_identity_fetcher"),
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
