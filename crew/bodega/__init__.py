"""Bodega: conteo con SAM 3.1 + voz."""

from crew.bodega.agent import BodegaAgent
from crew.bodega.sam import count_stock, parse_sam_output
from crew.bodega.voice import parse_stock_dictation, transcribe

__all__ = ["BodegaAgent", "count_stock", "parse_sam_output", "parse_stock_dictation", "transcribe"]
