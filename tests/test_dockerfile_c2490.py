"""C2490: la imagen debe traer todo lo que importa o lee el panel (modo en vivo)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = (ROOT / "Dockerfile").read_text()
COPIED = {m.group(1).split("/")[0] for m in re.finditer(r"^COPY\s+(\S+)\s+\S+", DOCKERFILE, re.M)}


def _local_packages() -> set[str]:
    return {p.name for p in ROOT.iterdir() if p.is_dir() and (p / "__init__.py").exists()}


def test_dockerfile_copies_every_package_imported_by_web_and_channels():
    local = _local_packages()
    imported: set[str] = set()
    for folder in ("web", "channels", "shield", "crew", "bendrix_shield"):
        for py in (ROOT / folder).rglob("*.py"):
            for m in re.finditer(r"^\s*(?:from|import)\s+([a-zA-Z_]+)", py.read_text(), re.M):
                if m.group(1) in local:
                    imported.add(m.group(1))
    missing = sorted(imported - COPIED - {"tests"})
    assert not missing, f"Dockerfile no copia: {missing}"


def test_dockerfile_copies_live_fixtures():
    for rel in ("evals/fixtures/live", "evals/advisories"):
        assert (ROOT / rel).is_dir()
        assert f"COPY {rel} " in DOCKERFILE
