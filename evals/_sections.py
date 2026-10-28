"""Escritura de secciones marcadas en evals/report.md (patrón de H5)."""

from __future__ import annotations

from pathlib import Path

REPORT = Path(__file__).parent / "report.md"


def write_section(start: str, end: str, text: str) -> None:
    current = REPORT.read_text(encoding="utf-8") if REPORT.is_file() else "# Evals\n"
    section = f"{start}\n{text}\n{end}"
    if start in current and end in current:
        before, rest = current.split(start, 1)
        _, after = rest.split(end, 1)
        current = before + section + after
    else:
        current = current.rstrip() + "\n\n" + section + "\n"
    REPORT.write_text(current, encoding="utf-8")
