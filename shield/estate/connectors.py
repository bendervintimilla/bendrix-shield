"""Conectores de inventario de SOLO LECTURA.

Cada conector expone ``list_assets() -> list[Asset]`` y ninguno escribe,
ejecuta ni guarda valores de secretos: de Railway solo salen nombres de
variables, de GCP solo restricciones/uso (proyecto configurado) y de
la web propia solo la versión detectada por header/meta, únicamente de
dominios en la allowlist. Todo es inyectable para tests.
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import yaml

from shield.schemas import Asset


def _configured_gcp_project() -> str:
    return (
        os.environ.get("SHIELD_GCP_PROJECT")
        or os.environ.get("GCP_PROJECT")
        or "configured-project"
    )


HACKATHON_PROJECT = _configured_gcp_project()


class EstateConnector(Protocol):
    name: str

    def list_assets(self) -> list[Asset]: ...


# -- Registro del gateway ------------------------------------------------------


class GatewayRegistryConnector:
    """Agentes, tokens y modelos desde el Registry SQLite del gateway."""

    name = "gateway-registry"

    def __init__(self, registry: Any) -> None:
        self._registry = registry

    def list_assets(self) -> list[Asset]:
        assets: list[Asset] = []
        for token in self._registry.list_tokens():
            assets.append(
                Asset(
                    id=token.token_id,
                    kind="shield_token",
                    name=token.agent,
                    owner_app=token.app,
                    platform="shield-gateway",
                    metadata={
                        "agent": token.agent,
                        "app": token.app,
                        "status": str(token.status),
                        "models": ",".join(token.models),
                        "scopes": ",".join(token.scopes),
                    },
                )
            )
        return assets


# -- Railway (sandbox): solo nombres de variables -------------------------------


class RailwayConnector:
    """Nombres de variables por servicio del sandbox. Jamás valores.

    ``provider`` devuelve ``{servicio: [nombres]}`` o ``{servicio: {nombre: valor}}``;
    en el segundo caso solo se toman las claves y el valor se descarta aquí.
    """

    name = "railway"

    def __init__(self, provider: Callable[[], Mapping[str, Any]]) -> None:
        self._provider = provider

    def list_assets(self) -> list[Asset]:
        assets: list[Asset] = []
        for service, variables in sorted(self._provider().items()):
            names = (
                sorted(variables.keys())
                if isinstance(variables, Mapping)
                else sorted(str(v) for v in variables)
            )
            assets.append(
                Asset(
                    id=f"railway-{service}",
                    kind="env_vars",
                    name=service,
                    owner_app=service,
                    platform="railway",
                    metadata={"var_names": ",".join(names), "var_count": str(len(names))},
                )
            )
        return assets


# -- GCP API keys: restricciones y uso ----------------------


class GcpApiKeysConnector:
    """Llaves de API de GCP del proyecto configurado: restricciones y uso.

    ``lister`` devuelve dicts con name/display_name/restrictions/usage. Se
    rechaza cualquier proyecto que no sea el configurado y
    nunca se recoge el valor de la llave, solo last4 si la fuente lo trae.
    """

    name = "gcp-api-keys"

    def __init__(
        self, lister: Callable[[], list[dict[str, Any]]], *, project: str | None = None
    ) -> None:
        allowed = _configured_gcp_project()
        if project is None:
            project = allowed
        if project != allowed:
            raise ValueError(f"solo se permite el proyecto {allowed}")
        self._lister = lister
        self.project = project

    def list_assets(self) -> list[Asset]:
        assets: list[Asset] = []
        for key in self._lister():
            name = str(key.get("display_name") or key.get("name") or "gcp-key")
            restrictions = key.get("restrictions") or {}
            usage = key.get("usage") or {}
            assets.append(
                Asset(
                    id=f"gcp-{name}",
                    kind="gcp_api_key",
                    name=name,
                    owner_app=self.project,
                    platform="gcp",
                    last4=str(key["last4"]) if key.get("last4") else None,
                    metadata={
                        "restrictions": json.dumps(restrictions, sort_keys=True, default=str)[:500],
                        "usage": json.dumps(usage, sort_keys=True, default=str)[:500],
                    },
                )
            )
        return assets


# -- Lockfiles de GitHub -> SBOM -------------------------------------------------


def _sbom_assets(deps: list[tuple[str, str, str]], source: str) -> list[Asset]:
    return [
        Asset(
            id=f"sbom-{source}-{name}-{version}",
            kind="pkg",
            name=name,
            platform="github",
            metadata={"version": version, "ecosystem": ecosystem, "source": source},
        )
        for name, version, ecosystem in deps
    ]


def parse_package_lock(text: str, *, source: str = "package-lock.json") -> list[Asset]:
    data = json.loads(text)
    deps: list[tuple[str, str, str]] = []
    packages = data.get("packages") or {}
    for path, info in packages.items():
        if not path.startswith("node_modules/") or not isinstance(info, dict):
            continue
        name = path.split("node_modules/")[-1]
        if info.get("version"):
            deps.append((name, str(info["version"]), "npm"))
    if not deps:  # lockfile v1
        for name, info in (data.get("dependencies") or {}).items():
            if isinstance(info, dict) and info.get("version"):
                deps.append((str(name), str(info["version"]), "npm"))
    return _sbom_assets(sorted(set(deps)), source)


def parse_requirements(text: str, *, source: str = "requirements.txt") -> list[Asset]:
    deps: list[tuple[str, str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        match = re.match(r"^([A-Za-z0-9_.\-]+)\s*(?:==|>=|~=)?\s*([0-9][^\s;,\[]*)?", line)
        if match:
            deps.append((match.group(1).lower(), match.group(2) or "", "pypi"))
    return _sbom_assets(deps, source)


def parse_uv_lock(text: str, *, source: str = "uv.lock") -> list[Asset]:
    data = tomllib.loads(text)
    deps = [
        (str(p["name"]).lower(), str(p.get("version") or ""), "pypi")
        for p in data.get("package") or []
        if p.get("name")
    ]
    return _sbom_assets(sorted(set(deps)), source)


class GithubSbomConnector:
    """SBOM desde lockfiles (contenido o ruta), sin salir a la red."""

    name = "github-sbom"

    def __init__(self, lockfiles: Mapping[str, str]) -> None:
        self._lockfiles = dict(lockfiles)  # nombre de archivo -> contenido

    @classmethod
    def from_paths(cls, paths: list[str | Path]) -> GithubSbomConnector:
        return cls({Path(p).name: Path(p).read_text(encoding="utf-8") for p in paths})

    def list_assets(self) -> list[Asset]:
        assets: list[Asset] = []
        for filename, text in sorted(self._lockfiles.items()):
            if filename == "package-lock.json":
                assets.extend(parse_package_lock(text, source=filename))
            elif filename == "requirements.txt":
                assets.extend(parse_requirements(text, source=filename))
            elif filename == "uv.lock":
                assets.extend(parse_uv_lock(text, source=filename))
        return assets


# -- Web propia (solo allowlist): versión por header o meta ---------------------


_PHP_RE = re.compile(r"PHP/([0-9][0-9A-Za-z.\-]*)", re.I)
_GENERATOR_RE = re.compile(
    r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)["\']', re.I
)
_VERSION_RE = re.compile(r"([A-Za-z][A-Za-z0-9 ._\-]*?)\s*v?([0-9]+\.[0-9]+[0-9A-Za-z.\-]*)")


class WebAllowlistConnector:
    """Versión de PHP/CMS de webs propias, solo header o meta. Sin explotar.

    ``fetcher(url) -> (headers, html)`` es inyectable. Cualquier dominio
    fuera de la allowlist se rechaza antes de pedir nada.
    """

    name = "web-allowlist"

    def __init__(
        self,
        urls: list[str],
        *,
        allowlist: set[str] | list[str],
        fetcher: Callable[[str], tuple[Mapping[str, str], str]],
    ) -> None:
        self._allowed = {d.lower() for d in allowlist}
        self._fetcher = fetcher
        for url in urls:
            host = (urlparse(url).hostname or "").lower()
            if host not in self._allowed:
                raise ValueError(f"dominio fuera de la allowlist: {host}")
        self._urls = list(urls)

    @classmethod
    def from_allowlist_yaml(
        cls,
        path: str | Path,
        urls: list[str],
        *,
        fetcher: Callable[[str], tuple[Mapping[str, str], str]],
    ) -> WebAllowlistConnector:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        domains = data.get("allowed_domains") or data.get("allowed_hosts") or []
        return cls(urls, allowlist=[str(d) for d in domains], fetcher=fetcher)

    def list_assets(self) -> list[Asset]:
        assets: list[Asset] = []
        for url in self._urls:
            headers, html = self._fetcher(url)
            powered = next((v for k, v in headers.items() if k.lower() == "x-powered-by"), "")
            php = _PHP_RE.search(powered)
            generator = _GENERATOR_RE.search(html or "")
            if php:
                name, version = "php", php.group(1)
            elif generator:
                matched = _VERSION_RE.search(generator.group(1))
                name = generator.group(1).split()[0].lower() if generator.group(1) else "cms"
                version = matched.group(2) if matched else ""
            else:
                name, version = "web", ""
            host = urlparse(url).hostname or url
            assets.append(
                Asset(
                    id=f"web-{host}",
                    kind="web",
                    name=name,
                    owner_app=host,
                    platform="web",
                    metadata={"version": version, "url": url},
                )
            )
        return assets


def collect_assets(connectors: list[EstateConnector]) -> list[Asset]:
    """Junta el inventario de todos los conectores (solo lectura)."""
    assets: list[Asset] = []
    for connector in connectors:
        assets.extend(connector.list_assets())
    return assets
