"""Cambia la marca pública en un solo comando.

Uso: ``uv run python scripts/set_brand.py NUEVO_NOMBRE [--dry-run]``

Actualiza ``shield/brand.py`` (única fuente en código) y reemplaza el
nombre anterior en textos no-código: ``README.md``, ``pyproject.toml``,
``docs/**/*.md``, ``docs/brand/*.svg``, ``docs/brand/slides/*.svg``,
``web/README.md`` y ``shield/README.md``. De ``evals/`` solo reemplaza
la línea de título ``# Evals de <nombre>`` de ``evals/report.md`` y nada
más de ese archivo. Al reemplazar solo el nombre exacto anterior se
conservan literalmente ``bendrix_shield``, ``bendrix-shield`` y las
URLs de Cloud Run.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_BRAND_RE = re.compile(r'^BRAND\s*=\s*"([^"]*)"', re.MULTILINE)
_REPORT_TITLE_RE = re.compile(r"^# Evals de \S+")


def current_brand(root: Path) -> str:
    text = (root / "shield" / "brand.py").read_text(encoding="utf-8")
    match = _BRAND_RE.search(text)
    if not match:
        raise ValueError("no se encontró BRAND en shield/brand.py")
    return match.group(1)


def target_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for rel in ("README.md", "pyproject.toml", "web/README.md", "shield/README.md"):
        path = root / rel
        if path.is_file():
            files.append(path)
    docs = root / "docs"
    if docs.is_dir():
        files.extend(sorted(docs.rglob("*.md")))
        files.extend(sorted((docs / "brand").glob("*.svg")))
        files.extend(sorted((docs / "brand" / "slides").glob("*.svg")))
    # Sin duplicados, en orden estable.
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in files:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def apply_brand(root: Path, new_name: str, *, dry_run: bool = False) -> list[Path]:
    new_name = new_name.strip()
    if not new_name or any(ch in new_name for ch in '"\\\n\r'):
        raise ValueError("nombre de marca inválido")
    old_name = current_brand(root)
    changed: list[Path] = []
    brand_file = root / "shield" / "brand.py"
    text = brand_file.read_text(encoding="utf-8")
    new_text = _BRAND_RE.sub(lambda _: f'BRAND = "{new_name}"', text, count=1)
    if new_text != text:
        changed.append(brand_file)
        if not dry_run:
            brand_file.write_text(new_text, encoding="utf-8")
    if old_name and old_name != new_name:
        for path in target_files(root):
            content = path.read_text(encoding="utf-8")
            if old_name in content:
                changed.append(path)
                if not dry_run:
                    path.write_text(content.replace(old_name, new_name), encoding="utf-8")
    # De evals/report.md solo la línea de título, nada más.
    report = root / "evals" / "report.md"
    if report.is_file():
        lines = report.read_text(encoding="utf-8").splitlines(keepends=True)
        for index, line in enumerate(lines):
            if _REPORT_TITLE_RE.match(line):
                new_line = _REPORT_TITLE_RE.sub(f"# Evals de {new_name}", line, count=1)
                if new_line != line:
                    lines[index] = new_line
                    changed.append(report)
                    if not dry_run:
                        report.write_text("".join(lines), encoding="utf-8")
                break
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cambia la marca pública (shield/brand.py).")
    parser.add_argument("new_name", help="nuevo nombre público, ej. NoKey")
    parser.add_argument("--dry-run", action="store_true", help="solo muestra qué cambiaría")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    old = current_brand(args.root)
    changed = apply_brand(args.root, args.new_name, dry_run=args.dry_run)
    mode = "dry-run, sin cambios" if args.dry_run else "actualizados"
    print(f"marca: {old} -> {args.new_name.strip()} ({mode}: {len(changed)} archivos)")
    for path in changed:
        print(f"  {path.relative_to(args.root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
