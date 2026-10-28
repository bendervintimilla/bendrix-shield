"""``wrap(client, token)``: apunta un cliente OpenAI al gateway de Shield.

La app nunca guarda la llave real del proveedor: solo su token Shield
(``shd_<agente>_…``), revocable al instante y por agente.
"""

from __future__ import annotations

import os
from typing import Any

DEFAULT_GATEWAY_URL = "http://127.0.0.1:8000/v1"


def gateway_url() -> str:
    return os.environ.get("SHIELD_GATEWAY_URL") or DEFAULT_GATEWAY_URL


def wrap(client: Any, token: str | None = None, *, base_url: str | None = None) -> Any:
    """Devuelve el mismo cliente, ya apuntado a Shield con ``token``.

    Uso (2 líneas)::

        client = wrap(OpenAI(api_key="shd_…"), "shd_…")
        client = wrap(OpenAI(), token)  # cualquier cliente estilo OpenAI
    """
    resolved = token or os.environ.get("SHIELD_TOKEN")
    if not resolved:
        raise ValueError("Shield token required: pass token= or set SHIELD_TOKEN")
    if not resolved.startswith("shd_"):
        raise ValueError("Shield token must start with 'shd_'")
    url = (base_url or gateway_url()).rstrip("/")
    # El SDK de OpenAI guarda base_url como httpx.URL; asignar str funciona
    # porque el cliente lo normaliza en la siguiente petición, pero para
    # clientes reales convertimos con su propio tipo si hace falta.
    try:
        import httpx

        client.base_url = httpx.URL(url + "/")
    except Exception:
        client.base_url = url
    client.api_key = resolved
    return client
