"""Reexporta la marca pública desde shield.brand (única fuente) y sus piezas web."""

from __future__ import annotations

import html

from shield.brand import BRAND, SUBTITLE

__all__ = ["BRAND", "SUBTITLE", "ACCENT", "brand_parts", "brand_mark_html", "favicon_href"]

# Color de acento de la marca (el «AI» resaltado; mismo ámbar del logo).
ACCENT = "#E8A33D"


def brand_parts(brand: str = BRAND) -> list[tuple[str, str]]:
    """Parte el nombre en tramos (``plain``/``ai``): «wAIrrior» → w · AI · rrior.

    Si el nombre no trae «ai», se resaltan sus 2 primeras letras.
    """
    i = brand.lower().find("ai")
    if i >= 0:
        parts = [("plain", brand[:i]), ("ai", brand[i : i + 2]), ("plain", brand[i + 2 :])]
    else:
        parts = [("ai", brand[:2]), ("plain", brand[2:])]
    return [(kind, text) for kind, text in parts if text]


def brand_mark_html(brand: str = BRAND, *, ai_class: str = "brand-ai") -> str:
    """Nombre en línea con el «AI» envuelto en un span para resaltarlo."""
    out = []
    for kind, text in brand_parts(brand):
        safe = html.escape(text, quote=True)
        out.append(f"<span class='{ai_class}'>{safe}</span>" if kind == "ai" else safe)
    return "".join(out)


def favicon_href(brand: str = BRAND) -> str:
    """Favicon SVG en data URI con la inicial de la marca («w») en el acento.

    El ``xmlns`` va con los dos puntos y las barras codificados: así el SVG es
    válido y la página no trae ningún ``http://`` literal.
    """
    initial = html.escape((brand[:1] or "w"), quote=True)
    return (
        "data:image/svg+xml,%3Csvg xmlns='http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg' "
        "viewBox='0 0 64 64'%3E"
        "%3Crect width='64' height='64' rx='14' fill='%23111113'/%3E"
        "%3Ctext x='32' y='44' font-family='system-ui,sans-serif' font-size='38' font-weight='700' "
        f"fill='%23E8A33D' text-anchor='middle'%3E{initial}%3C/text%3E%3C/svg%3E"
    )
