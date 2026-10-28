"""Interfaz del clasificador de salida (Muse Spark Open).

H3 deja la interfaz y un stub determinista que **no bloquea nada**.
H9 lo reemplaza por Spark Open (``meta-models/muse-spark-open-1026``)
sin cambiar esta firma.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Classification:
    label: str = "unclassified"
    score: float = 0.0
    model: str = "stub"
    reason: str = "classifier not configured (H9: Spark Open)"


@runtime_checkable
class Classifier(Protocol):
    def classify(self, text: str) -> Classification: ...


class StubClassifier:
    """Stub honesto: etiqueta todo como no clasificado, jamás bloquea."""

    def classify(self, text: str) -> Classification:
        return Classification()


_default: Classifier = StubClassifier()


def set_classifier(classifier: Classifier) -> None:
    global _default
    _default = classifier


def get_classifier() -> Classifier:
    return _default


def classify(text: str, *, classifier: Classifier | None = None) -> Classification:
    return (classifier or _default).classify(text)
