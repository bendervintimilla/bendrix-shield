"""Lectores de avisos públicos -> ThreatCard.

Parsers puros (sin red) para CISA KEV, OSV/GHSA, RSS/Atom y status de
proveedores, más un fetch con caché en disco (replay): la segunda lectura
del mismo URL sale del caché y los tests corren sin red. El contenido de un
feed es dato no confiable: aquí solo se normaliza a ThreatCard, nunca se
ejecutan instrucciones que traiga.
"""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from shield.schemas import Product, ThreatCard

KEV_CATALOG_URL = "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")[:80] or "aviso"


# -- CISA KEV ---------------------------------------------------------------


def parse_kev(payload: dict[str, Any], *, source_url: str = KEV_CATALOG_URL) -> list[ThreatCard]:
    """Catálogo KEV: cada vulnerabilidad explotada es una ThreatCard."""
    cards: list[ThreatCard] = []
    for vuln in payload.get("vulnerabilities") or []:
        cve = str(vuln.get("cveID") or "").strip()
        if not cve:
            continue
        product = str(vuln.get("product") or vuln.get("vendorProject") or "unknown")
        actions = [str(vuln["requiredAction"])] if vuln.get("requiredAction") else []
        cards.append(
            ThreatCard(
                id=cve,
                source_url=f"https://www.cve.org/CVERecord?id={cve}",
                published_at=_dt(vuln.get("dateAdded")),
                products=[Product(name=product, ecosystem=str(vuln.get("vendorProject") or ""))],
                iocs=[cve],
                actions=actions,
                severity="high",  # KEV = explotación conocida
            )
        )
    return cards


# -- OSV / GHSA (mismo esquema OSV) ------------------------------------------


def _osv_card(vuln: dict[str, Any], source_url: str) -> ThreatCard | None:
    vid = str(vuln.get("id") or "").strip()
    if not vid:
        return None
    products: list[Product] = []
    for affected in vuln.get("affected") or []:
        pkg = affected.get("package") or {}
        name = str(pkg.get("name") or "").strip()
        if not name:
            continue
        affected_versions = [str(v) for v in (affected.get("versions") or [])]
        fixed: list[str] = []
        for rng in affected.get("ranges") or []:
            for event in rng.get("events") or []:
                if "fixed" in event:
                    fixed.append(str(event["fixed"]))
                if "introduced" in event and str(event["introduced"]) not in ("0", ""):
                    affected_versions.append(f">={event['introduced']}")
        products.append(
            Product(
                name=name,
                ecosystem=str(pkg.get("ecosystem") or "") or None,
                affected_versions=affected_versions,
                fixed_versions=fixed,
            )
        )
    severity = None
    db = vuln.get("database_specific") or {}
    if db.get("severity"):
        severity = str(db["severity"]).lower()
    refs = [str(r.get("url")) for r in (vuln.get("references") or []) if r.get("url")]
    aliases = [str(a) for a in (vuln.get("aliases") or [])]
    return ThreatCard(
        id=vid,
        source_url=refs[0] if refs else source_url,
        published_at=_dt(vuln.get("published")),
        products=products,
        iocs=aliases,
        actions=["upgrade"] if any(p.fixed_versions for p in products) else [],
        severity=severity,
    )


def parse_osv(payload: dict[str, Any], *, source_url: str = "https://osv.dev/") -> list[ThreatCard]:
    vulns = payload.get("vulns") or ([payload] if payload.get("id") else [])
    return [c for v in vulns if (c := _osv_card(v, source_url)) is not None]


def parse_ghsa(
    payload: dict[str, Any], *, source_url: str = "https://github.com/advisories"
) -> list[ThreatCard]:
    items = payload if isinstance(payload, list) else payload.get("vulns") or [payload]
    cards: list[ThreatCard] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        # La API REST de GHSA trae vulnerabilities[]; se adapta a la forma OSV.
        if "vulnerabilities" in item and "affected" not in item:
            affected = [
                {
                    "package": {
                        "name": (v.get("package") or {}).get("name", ""),
                        "ecosystem": (v.get("package") or {}).get("ecosystem", ""),
                    },
                    "versions": [v["vulnerable_version_range"]]
                    if v.get("vulnerable_version_range")
                    else [],
                    "ranges": [],
                }
                for v in item.get("vulnerabilities") or []
            ]
            item = {
                **item,
                "id": item.get("ghsa_id") or item.get("cve_id") or "",
                "affected": affected,
                "published": item.get("published_at"),
            }
        card = _osv_card(item, source_url)
        if card is not None:
            cards.append(card)
    return cards


# -- RSS / Atom ---------------------------------------------------------------


def parse_rss(xml_text: str, *, source_url: str) -> list[ThreatCard]:
    root = ET.fromstring(xml_text)
    cards: list[ThreatCard] = []
    # RSS 2.0: channel/item; Atom: entry (con namespace).
    items = root.findall(".//item")
    if not items:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for item in items:

        def text_of(*tags: str) -> str:
            for tag in tags:
                el = item.find(tag)
                if el is not None and el.text:
                    return el.text.strip()
            return ""

        title = text_of("title", "{http://www.w3.org/2005/Atom}title")
        link = text_of("link", "guid")
        if not link:
            link_el = item.find("{http://www.w3.org/2005/Atom}link")
            link = (link_el.get("href") or source_url) if link_el is not None else source_url
        published = text_of("pubDate", "published", "updated")
        parsed_dt = None
        if published:
            try:
                from email.utils import parsedate_to_datetime

                parsed_dt = parsedate_to_datetime(published)
            except (TypeError, ValueError):
                parsed_dt = _dt(published)
        cards.append(
            ThreatCard(
                id=f"rss-{_slug(title) or hashlib.sha256(link.encode()).hexdigest()[:12]}",
                source_url=link or source_url,
                published_at=parsed_dt,
                products=[],
                iocs=[],
                actions=[],
                severity=None,
            )
        )
    return cards


# -- Status de proveedores (formato statuspage.io) ----------------------------


def parse_status(payload: dict[str, Any], *, source_url: str) -> list[ThreatCard]:
    cards: list[ThreatCard] = []
    provider = str(((payload.get("page") or {}).get("name")) or "provider")
    for incident in payload.get("incidents") or []:
        name = str(incident.get("name") or "incident")
        impact = str(incident.get("impact") or "minor").lower()
        severity = {"critical": "critical", "major": "high", "minor": "medium"}.get(impact, "low")
        cards.append(
            ThreatCard(
                id=f"status-{_slug(provider)}-{_slug(str(incident.get('id') or name))}",
                source_url=str(incident.get("shortlink") or source_url),
                published_at=_dt(incident.get("created_at")),
                products=[Product(name=provider, ecosystem="platform")],
                iocs=[],
                actions=["check_status", "verify"],
                severity=severity,
            )
        )
    return cards


PARSERS: dict[str, Callable[..., list[ThreatCard]]] = {
    "kev": parse_kev,
    "osv": parse_osv,
    "ghsa": parse_ghsa,
    "rss": parse_rss,
    "status": parse_status,
}


# -- Fetch con caché / replay --------------------------------------------------


class FeedCache:
    """Caché en disco por hash del URL: replay sin red para demo y tests."""

    def __init__(self, cache_dir: str | Path) -> None:
        self.cache_dir = Path(cache_dir)

    def _path(self, url: str) -> Path:
        return self.cache_dir / f"{hashlib.sha256(url.encode()).hexdigest()[:24]}.txt"

    def get(self, url: str) -> str | None:
        path = self._path(url)
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def put(self, url: str, text: str) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._path(url).write_text(text, encoding="utf-8")


def fetch_feed(
    url: str,
    kind: str,
    *,
    cache: FeedCache | None = None,
    transport: httpx.BaseTransport | None = None,
    timeout_s: float = 30.0,
) -> list[ThreatCard]:
    """Descarga (o lee del caché) un feed y lo normaliza a ThreatCard."""
    parser = PARSERS[kind]
    text = cache.get(url) if cache is not None else None
    if text is None:
        with httpx.Client(transport=transport, timeout=timeout_s, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "bendrix-shield-watch/0.1"})
            resp.raise_for_status()
            text = resp.text
        if cache is not None:
            cache.put(url, text)
    if kind == "rss":
        return parser(text, source_url=url)
    return parser(json.loads(text), source_url=url)


def now_utc() -> datetime:
    return datetime.now(UTC)
