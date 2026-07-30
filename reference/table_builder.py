"""
Assembles a complete schedule-table object: runs anchor detection,
clips a candidate region below each anchor, attempts grid-based
reconstruction (primary strategy), and assigns extracted text into
cells. This is the only function downstream exporters/validation
should call.

NOT yet wired in this pass (deliberately -- keeps Phase 1 focused):
  - text_clustering.py fallback for regions with no usable grid
  - header_normalizer.py canonical-field mapping
  - rebar_notation.py cell-value parsing
These are the natural next modules once this raw extraction is
validated against a real benchmark PDF.
"""

from __future__ import annotations
import fitz

from .anchor_detection import find_schedule_anchors, ScheduleAnchor
from .grid_reconstructor import GridLine, extract_grid_lines, build_grid, detect_merged_header_cells
from .rebar_notation import parse_rebar_value


HARD_SEARCH_CAP = 900.0    # pts; safety-net max search depth only -- not the real table boundary
REGION_SIDE_MARGIN = 20.0  # pts; horizontal padding around the anchor's own bbox
MAX_ROW_GAP = 40.0         # pts; a gap this large between consecutive horizontal rulings means
                           # the table has ended (e.g. transitioning into a detail drawing --
                           # see Image 1, where "General Section of Beam" sits just below the table)


def clip_region_below_anchor(anchor: ScheduleAnchor, page_rect: fitz.Rect) -> fitz.Rect:
    """
    Generous initial search window below the anchor, bounded only by
    HARD_SEARCH_CAP as an absolute safety net. Real trimming happens
    in refine_region_bottom() once the actual ruling geometry is
    visible -- a fixed pixel height would risk sweeping a detail
    drawing sitting just below the schedule into the table region.
    """
    return fitz.Rect(
        max(page_rect.x0, anchor.bbox.x0 - REGION_SIDE_MARGIN),
        anchor.bbox.y1,
        page_rect.x1,
        min(page_rect.y1, anchor.bbox.y1 + HARD_SEARCH_CAP),
    )


def refine_region_bottom(region: fitz.Rect, lines: list[GridLine]) -> tuple[fitz.Rect, list[GridLine]]:
    """
    Trims the region's bottom edge to the end of the actual contiguous
    ruling block instead of trusting a fixed height. Walks the sorted
    horizontal-ruling y-positions and stops at the first gap larger
    than MAX_ROW_GAP -- everything past that point (e.g. a detail
    drawing's own lines) is dropped from consideration.

    Returns the trimmed region AND the line list filtered to that
    bound, since build_grid() should only see rulings within it.
    """
    row_ys = sorted({round(l.position, 1) for l in lines if l.orientation == "horizontal"})
    if len(row_ys) < 2:
        return region, lines  # nothing to trim against; let build_grid() fail cleanly instead

    bottom = row_ys[0]
    for y in row_ys[1:]:
        if y - bottom > MAX_ROW_GAP:
            break
        bottom = y

    trimmed_region = fitz.Rect(region.x0, region.y0, region.x1, bottom)
    filtered_lines = [
        l for l in lines
        if not (l.orientation == "horizontal" and l.position > bottom + 1)
    ]
    return trimmed_region, filtered_lines


def extract_cell_text(page: fitz.Page, cell: fitz.Rect) -> str:
    """
    Pulls all text whose word-bbox center falls inside the cell
    rectangle. Using centers (not full containment) avoids losing
    text that slightly overhangs a ruling line.
    """
    words = page.get_text("words")  # (x0, y0, x1, y1, word, block_no, line_no, word_no)
    matched = []
    for w in words:
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        if cell.x0 <= cx <= cell.x1 and cell.y0 <= cy <= cell.y1:
            matched.append(w[4])
    return " ".join(matched)


def build_table_from_anchor(page: fitz.Page, anchor: ScheduleAnchor, page_rect: fitz.Rect) -> dict | None:
    search_region = clip_region_below_anchor(anchor, page_rect)
    raw_lines = extract_grid_lines(page, search_region)
    region, lines = refine_region_bottom(search_region, raw_lines)
    grid = build_grid(lines)

    if grid is None:
        # TODO (Phase 1.5): fall back to text_clustering.cluster_by_text_position(page, region)
        return None

    detect_merged_header_cells(grid, lines, header_row_count=1)

    n_cols = len(grid.col_positions) - 1
    n_rows = len(grid.row_positions) - 1
    rows = []
    for r in range(n_rows):
        row_cells = []
        for c in range(n_cols):
            cell_rect = grid.cells[r * n_cols + c]
            raw_text = extract_cell_text(page, cell_rect)
            row_cells.append({
                "col_index": c,
                "raw_text": raw_text,
                # Vector-extracted text is exact (no OCR involved), so confidence is a constant
                # here rather than a model score -- kept for schema consistency with the raster path.
                "confidence": 1.0,
                "normalized_value": parse_rebar_value(raw_text),
                "bbox": [cell_rect.x0, cell_rect.y0, cell_rect.x1, cell_rect.y1],
            })
        rows.append({"row_index": r, "cells": row_cells})

    return {
        "table_type": anchor.table_type,
        "title_raw": anchor.matched_text,
        "source_region_bbox": [region.x0, region.y0, region.x1, region.y1],
        "row_count": n_rows,
        "col_count": n_cols,
        "header_row_index": 0,  # assumption: first row is header -- revisit once merge detection is validated
        "merged_header_cells": grid.merged_header_cells,  # list of {"bbox": [...], "merge_type": "horizontal"|"vertical"}
        "rows": rows,
    }


def extract_all_tables(pdf_path: str) -> list[dict]:
    """Entry point: opens a PDF, finds every schedule anchor on every
    page, and attempts to build a table for each one."""
    doc = fitz.open(pdf_path)
    tables = []
    for page_number, page in enumerate(doc, start=1):
        # NOTE: PyMuPDF applies the page's /Rotate transform automatically to both
        # get_text() and get_drawings(), so a rotated sheet (e.g. a landscape-authored
        # page viewed portrait) *should* already land in a consistent coordinate space.
        # This has not yet been verified against a real rotated benchmark PDF --
        # if row/column detection looks wrong on such a sheet, check page.rotation
        # first before assuming the grid-reconstruction logic itself is at fault.
        for anchor in find_schedule_anchors(page, page_number):
            table = build_table_from_anchor(page, anchor, page.rect)
            if table:
                table["page_number"] = page_number
                tables.append(table)
    return tables


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print("Usage: python -m tables.table_builder <path_to_pdf>")
        sys.exit(1)

    results = extract_all_tables(sys.argv[1])
    print(json.dumps(results, indent=2))
