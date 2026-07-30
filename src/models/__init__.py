"""
Data models for the schedule extraction pipeline.

Uses dataclasses to match the existing code style. These replace the
earlier Dimension/Geometry models — the pipeline now produces Table,
TableHeader, TableRow, and Cell objects that map directly to the
canonical JSON schema (see schemas/schedule_schema_example.json).

Every raw extracted value is preserved alongside its normalized/parsed
form — we never discard the original text.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Cell:
    """A single cell in a schedule table row."""
    col_index: int
    raw_text: str
    normalized_value: Any = None  # Parsed value (rebar groups, dimensions, etc.) or None
    confidence: float = 1.0       # 1.0 for vector-extracted text; will vary once OCR path exists
    bbox: list[float] = field(default_factory=list)  # [x0, y0, x1, y1]

    def to_dict(self) -> dict:
        return {
            "col_index": self.col_index,
            "raw_text": self.raw_text,
            "normalized_value": self.normalized_value,
            "confidence": self.confidence,
            "bbox": self.bbox,
        }


@dataclass
class TableHeader:
    """
    A column header in a schedule table.

    parent_header is set when this header is a sub-column under a merged
    parent (e.g. "STR." under "BOTTAM REINFO." in a beam schedule).
    canonical_field comes from header_normalizer.py's fuzzy matching.
    """
    col_index: int
    raw_header: str
    canonical_field: str | None = None  # Set by header_normalizer
    parent_header: str | None = None    # Raw text of the merged parent, if any

    def to_dict(self) -> dict:
        return {
            "col_index": self.col_index,
            "raw_header": self.raw_header,
            "canonical_field": self.canonical_field,
            "parent_header": self.parent_header,
        }


@dataclass
class TableRow:
    """A data row in a schedule table (excludes header rows)."""
    row_index: int
    cells: list[Cell] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "row_index": self.row_index,
            "cells": [c.to_dict() for c in self.cells],
        }


@dataclass
class MergedHeaderCell:
    """Records a detected merged cell in the header band."""
    bbox: list[float]               # [x0, y0, x1, y1]
    merge_type: str                  # "horizontal" or "vertical"

    def to_dict(self) -> dict:
        return {"bbox": self.bbox, "merge_type": self.merge_type}


@dataclass
class Table:
    """
    A fully extracted schedule table — the top-level output object.

    This is the canonical representation that exporters (JSON, CSV, debug
    overlay) consume. Corresponds to one entry in the output schema's
    "tables" array.
    """
    table_type: str                  # e.g. "beam_schedule", "insert_schedule"
    title_raw: str                   # Exact text of the schedule title as extracted
    page_number: int = 0
    source_region_bbox: list[float] = field(default_factory=list)
    row_count: int = 0
    col_count: int = 0
    header_row_index: int = 0
    headers: list[TableHeader] = field(default_factory=list)
    merged_header_cells: list[MergedHeaderCell] = field(default_factory=list)
    rows: list[TableRow] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "table_type": self.table_type,
            "title_raw": self.title_raw,
            "page_number": self.page_number,
            "source_region_bbox": self.source_region_bbox,
            "row_count": self.row_count,
            "col_count": self.col_count,
            "header_row_index": self.header_row_index,
            "headers": [h.to_dict() for h in self.headers],
            "merged_header_cells": [m.to_dict() for m in self.merged_header_cells],
            "rows": [r.to_dict() for r in self.rows],
        }
