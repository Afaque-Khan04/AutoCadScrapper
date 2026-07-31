"""
Locates candidate schedule-table anchors on a PDF page by searching for
known schedule title keywords (e.g. "SCHEDULE OF BEAMS", "Weight Schedule").
Each match returns a ScheduleAnchor with the bbox of the title text so
downstream table-detection modules can search immediately below/around it.

This intentionally does NOT try to detect tables generically across the
whole page — engineering drawings almost always label their schedules
with a consistent title convention, so anchoring on that text is far
more reliable than blind grid-hunting across a busy sheet full of
layout geometry, notes, and title-block content.

Changes from reference baseline:
  - Imports patterns from src.utils.constants (single source of truth)
  - Pre-compiled regex patterns instead of re-compiling per call
  - Added exclusion patterns (e.g. "REVISION SCHEDULE") to avoid
    false positives from title-block metadata
"""

from __future__ import annotations
from dataclasses import dataclass
import fitz  # PyMuPDF

from ..utils.constants import (
    SCHEDULE_TITLE_PATTERNS,
    SCHEDULE_TITLE_EXCLUSIONS,
    NOTES_TITLE_PATTERNS,
)


@dataclass
class ScheduleAnchor:
    table_type: str          # e.g. "beam_schedule", "insert_schedule", "general_notes"
    matched_text: str        # the raw text PyMuPDF matched
    bbox: fitz.Rect          # bounding box of the title text itself
    page_number: int
    region_type: str = "schedule"  # "schedule", "general_notes", "legend", "specifications"


def find_schedule_anchors(
    page: fitz.Page,
    page_number: int,
    include_notes: bool = False,
) -> list[ScheduleAnchor]:
    """
    Scans a page's text for schedule-title keywords (and optionally notes-title
    keywords if include_notes=True) and returns one ScheduleAnchor per match.
    """
    anchors: list[ScheduleAnchor] = []
    blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, block_type)

    for block in blocks:
        # block_type 1 = image block; skip those
        if block[6] != 0:
            continue

        x0, y0, x1, y1, text = block[0], block[1], block[2], block[3], block[4]
        normalized = " ".join(text.split()).lower()

        # Check exclusions first — skip this block entirely if it matches
        if any(excl.search(normalized) for excl in SCHEDULE_TITLE_EXCLUSIONS):
            continue

        matched_block = False
        # 1. Search structural / precast schedule titles
        for table_type, patterns in SCHEDULE_TITLE_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(normalized):
                    anchors.append(
                        ScheduleAnchor(
                            table_type=table_type,
                            matched_text=text.strip(),
                            bbox=fitz.Rect(x0, y0, x1, y1),
                            page_number=page_number,
                            region_type="schedule",
                        )
                    )
                    matched_block = True
                    break
            if matched_block:
                break

        if matched_block:
            continue

        # 2. Search notes / legend titles if enabled
        if include_notes:
            for region_type, patterns in NOTES_TITLE_PATTERNS.items():
                for pattern in patterns:
                    if pattern.search(normalized):
                        anchors.append(
                            ScheduleAnchor(
                                table_type=region_type,
                                matched_text=text.strip(),
                                bbox=fitz.Rect(x0, y0, x1, y1),
                                page_number=page_number,
                                region_type=region_type,
                            )
                        )
                        matched_block = True
                        break
                if matched_block:
                    break

    return anchors


def find_all_anchors(page: fitz.Page, page_number: int) -> list[ScheduleAnchor]:
    """Scans page for both schedule and non-schedule (General Notes / Legend) anchors."""
    return find_schedule_anchors(page, page_number, include_notes=True)
