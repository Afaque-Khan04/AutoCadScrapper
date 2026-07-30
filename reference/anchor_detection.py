"""
Locates candidate schedule-table anchors on a PDF page by searching for
known schedule title keywords (e.g. "SCHEDULE OF BEAMS"). Each match
returns a bounding box that downstream table-detection modules use as a
starting region to search for a grid.

This intentionally does NOT try to detect tables generically across the
whole page -- engineering drawings almost always label their schedules
with a consistent title convention, so anchoring on that text is far
more reliable than blind grid-hunting across a busy sheet full of
layout geometry, notes, and title-block content.
"""

from __future__ import annotations
from dataclasses import dataclass
import re
import fitz  # PyMuPDF


# Known schedule title conventions. Extend this list as you encounter
# more benchmark drawings -- it is meant to grow, not be exhaustive on day one.
SCHEDULE_TITLE_PATTERNS: dict[str, list[str]] = {
    "beam_schedule": [r"schedule\s+of\s+beams?", r"beam\s+schedule"],
    "slab_schedule": [r"schedule\s+of\s+slabs?", r"slab\s+schedule"],
    "column_schedule": [r"schedule\s+of\s+columns?", r"column\s+schedule"],
    "reinforcement_schedule": [r"reinforcement\s+schedule", r"schedule\s+of\s+reinforcement"],
    "bar_bending_schedule": [r"bar\s+bending\s+schedule", r"\bbbs\b"],
    "material_schedule": [r"material\s+schedule", r"schedule\s+of\s+materials?"],
    "bill_of_materials": [r"bill\s+of\s+material", r"\bbom\b"],
}


@dataclass
class ScheduleAnchor:
    table_type: str          # e.g. "beam_schedule"
    matched_text: str        # the raw text PyMuPDF matched
    bbox: fitz.Rect           # bounding box of the title text itself
    page_number: int


def find_schedule_anchors(page: fitz.Page, page_number: int) -> list[ScheduleAnchor]:
    """
    Scans a page's text for schedule-title keywords and returns one
    ScheduleAnchor per match, each carrying the bbox of the title text
    so a table-region clipper can search immediately below/around it.

    Uses regex over full-page text blocks rather than exact string
    search, since spacing/casing varies ("SCHEDULE OF BEAMS" vs
    "Schedule Of Beams" vs "BEAM SCHEDULE").
    """
    anchors: list[ScheduleAnchor] = []
    blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, block_type)

    for block in blocks:
        x0, y0, x1, y1, text = block[0], block[1], block[2], block[3], block[4]
        normalized = " ".join(text.split()).lower()

        for table_type, patterns in SCHEDULE_TITLE_PATTERNS.items():
            matched_pattern = False
            for pattern in patterns:
                if re.search(pattern, normalized):
                    anchors.append(
                        ScheduleAnchor(
                            table_type=table_type,
                            matched_text=text.strip(),
                            bbox=fitz.Rect(x0, y0, x1, y1),
                            page_number=page_number,
                        )
                    )
                    matched_pattern = True
                    break
            if matched_pattern:
                break  # don't let one block match multiple table_types

    return anchors
