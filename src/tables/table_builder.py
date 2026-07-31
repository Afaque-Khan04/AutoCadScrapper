"""
Assembles a complete schedule-table object: runs anchor detection,
discovers actual table boundaries from nearby vector rulings, attempts
grid-based reconstruction (primary strategy), and assigns extracted
text into cells. This is the only function downstream exporters /
validation should call.

Table-bounds discovery strategy (replaces the earlier "page-width clip"):
  1. Narrow corridor scan below the anchor title (anchor_width × 3,
     limited depth) to find the first ruling lines.
  2. Identify the topmost horizontal ruling — this is the table's top
     edge.
  3. Find every vertical ruling that physically TOUCHES that top
     horizontal (within tolerance).
  4. Bracket x-bounds to the nearest verticals INSIDE the anchor's
     left/right extent — this correctly isolates each schedule's columns
     when multiple tables sit side-by-side sharing a common top horizontal.
  5. With the correct x-bounds locked, do a full vertical search
     (MAX_ROW_GAP bottom-trim) within those bounds.
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

import fitz

from .anchor_detection import find_schedule_anchors, ScheduleAnchor
from .grid_reconstructor import (
    GridLine, extract_grid_lines, build_grid, build_cell_rects, TableGrid,
    detect_merged_header_cells, COLLINEAR_MERGE_TOLERANCE,
)
from .text_clustering import build_text_grid
from .header_normalizer import normalize_header
from ..parsing.rebar_notation import parse_rebar_value


HARD_SEARCH_CAP = 900.0          # pts; absolute max vertical search depth
INITIAL_SCAN_DEPTH = 150.0       # pts; depth of the narrow initial corridor scan
INITIAL_WIDTH_MULTIPLIER = 3.0   # initial corridor = anchor_width × this
INITIAL_MIN_WIDTH = 200.0        # pts; minimum corridor width (handles short titles like "BBS")
BOUNDS_PADDING = 5.0             # pts; small padding around discovered x-bounds
TOUCH_TOLERANCE = 3.0            # pts; how close a vertical must be to a horizontal's span
MAX_ROW_GAP = 40.0               # pts; gap > this between consecutive horizontals = end of table

# Text-only fallback constants (used when no vector rulings exist)
TEXT_FALLBACK_LEFT_MARGIN = 0.7   # multiplier: margin left of anchor = anchor_width × this
TEXT_FALLBACK_RIGHT_MARGIN = 0.7  # multiplier: margin right of anchor = anchor_width × this
TEXT_FALLBACK_MIN_MARGIN = 40.0   # pts; minimum margin on each side
MIN_REGION_WIDTH = 30.0           # pts; region narrower than this is likely not a real table
ANCHOR_PROXIMITY_MULTIPLIER = 1.2 # multiplier: keep cols within anchor_center ± width × this

# Canonical fields whose cells should be parsed as rebar notation.
_REBAR_FIELDS = {
    "top_reinforcement", "bottom_reinforcement", "straight_bars",
    "bent_bars", "stirrups", "main_reinforcement", "distribution_bars",
    "spacing",
}


# ---------------------------------------------------------------------------
# Table-bounds discovery (two-pass)
# ---------------------------------------------------------------------------

def _discover_table_bounds(
    page: fitz.Page,
    anchor: ScheduleAnchor,
    page_rect: fitz.Rect,
) -> fitz.Rect | None:
    """
    Discovers the actual table boundary by searching around the anchor
    title for vector ruling lines, then using connectivity to determine
    the table's true extent.

    Handles two common layouts:
      A) Title ABOVE the table — rulings start below the anchor bbox
      B) Title INSIDE the table — the title sits in the first tall row
         of the grid, and rulings exist both above and below the title

    Algorithm:
      1. Scan a corridor centered on the anchor (above + below) for
         initial ruling lines.
      2. Find the topmost horizontal ruling — this is the table top.
      3. Find verticals that physically touch that top horizontal
         (connectivity check).
      4. Bracket x-bounds to the nearest verticals INSIDE the anchor's
         left/right extent — this correctly isolates each schedule's
         columns when multiple tables sit side-by-side sharing a common
         top horizontal.
      5. With x-bounds locked, return a region extending downward for
         full grid extraction.
    """
    # --- Pass 1: corridor scan around the anchor ---
    # Search both above (title might be inside the table) and below
    anchor_width = anchor.bbox.x1 - anchor.bbox.x0
    corridor_width = max(anchor_width * INITIAL_WIDTH_MULTIPLIER, INITIAL_MIN_WIDTH)
    center_x = (anchor.bbox.x0 + anchor.bbox.x1) / 2

    # Extend upward by 50pt (to catch table-top rulings when title is inside)
    # and downward by INITIAL_SCAN_DEPTH
    SCAN_ABOVE = 50.0

    corridor = fitz.Rect(
        max(page_rect.x0, center_x - corridor_width / 2),
        max(page_rect.y0, anchor.bbox.y0 - SCAN_ABOVE),
        min(page_rect.x1, center_x + corridor_width / 2),
        min(page_rect.y1, anchor.bbox.y1 + INITIAL_SCAN_DEPTH),
    )

    initial_lines = extract_grid_lines(page, corridor)

    horiz = sorted(
        [l for l in initial_lines if l.orientation == "horizontal"],
        key=lambda l: l.position,
    )
    if not horiz:
        return None  # no horizontal rulings found — no table here

    # --- Step 2: topmost horizontal = table top edge ---
    top_h = horiz[0]

    # --- Step 3: find verticals connected to the top horizontal ---
    # A vertical "touches" the top horizontal if:
    #   a) Its y-range overlaps the horizontal's y-position (within tolerance)
    #   b) Its x-position falls within the horizontal's x-span (within tolerance)
    verts = [l for l in initial_lines if l.orientation == "vertical"]
    connected_verts = [
        v for v in verts
        if (v.start <= top_h.position + TOUCH_TOLERANCE
            and v.end >= top_h.position - TOUCH_TOLERANCE)
        and (top_h.start - TOUCH_TOLERANCE <= v.position <= top_h.end + TOUCH_TOLERANCE)
    ]

    if not connected_verts:
        # Fallback: use the horizontal's own span as x-bounds
        x_left = top_h.start
        x_right = top_h.end
    else:
        # --- Step 4: bracket x-bounds around anchor's x-extent ---
        # For side-by-side schedules, the top horizontal often spans ALL
        # tables and ALL verticals touch it, so using outermost verticals
        # gives the shared combined bounds across all tables.
        # Instead, find the nearest vertical to the LEFT of the anchor's
        # left edge and the nearest vertical to the RIGHT of the anchor's
        # right edge — this correctly isolates each schedule's columns.
        anchor_x0 = anchor.bbox.x0
        anchor_x1 = anchor.bbox.x1

        left_verts = [v for v in connected_verts if v.position < anchor_x0 + TOUCH_TOLERANCE]
        right_verts = [v for v in connected_verts if v.position > anchor_x1 - TOUCH_TOLERANCE]

        if left_verts and right_verts:
            # Innermost pair bracketing the anchor
            x_left = max(v.position for v in left_verts)
            x_right = min(v.position for v in right_verts)
        else:
            # Fallback: outermost verticals (single table or edge case)
            x_left = min(v.position for v in connected_verts)
            x_right = max(v.position for v in connected_verts)

    # --- Step 5: return bounded region ---
    # Start from the table top (which may be above the anchor title)
    return fitz.Rect(
        x_left - BOUNDS_PADDING,
        top_h.position - BOUNDS_PADDING,
        x_right + BOUNDS_PADDING,
        min(page_rect.y1, top_h.position + HARD_SEARCH_CAP),
    )


# ---------------------------------------------------------------------------
# Region refinement (bottom edge)
# ---------------------------------------------------------------------------

def refine_region_bottom(
    region: fitz.Rect,
    lines: list[GridLine],
) -> tuple[fitz.Rect, list[GridLine]]:
    """
    Trims the region's bottom edge to the end of the actual contiguous
    ruling block instead of trusting a fixed height. Walks the sorted
    horizontal-ruling y-positions and stops at the first gap larger
    than MAX_ROW_GAP — everything past that point (e.g. a detail
    drawing's own lines) is dropped from consideration.

    Returns the trimmed region AND the line list filtered to that
    bound, since build_grid() should only see rulings within it.
    """
    row_ys = sorted({
        round(l.position, 1)
        for l in lines if l.orientation == "horizontal"
    })
    if len(row_ys) < 2:
        return region, lines

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


# ---------------------------------------------------------------------------
# Cell text extraction
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Header extraction and normalization
# ---------------------------------------------------------------------------

def _extract_headers(page: fitz.Page, grid, header_row_count: int = 1) -> list[dict]:
    """
    Extracts header text from the first header_row_count row(s) of
    the grid, normalizes each header to a canonical field name.

    Handles narrow header bands (e.g. Weight Schedule in the benchmark
    PDF) where header text may overflow the first row's boundaries.
    If a column's first-pass header is empty, performs an expanded
    vertical search covering the first two grid rows.

    Returns a list of header dicts matching the schema:
    [{"col_index": 0, "raw_header": "Ref No.", "canonical_field": "ref_no", "parent_header": None}, ...]
    """
    n_cols = len(grid.col_positions) - 1
    headers = []

    for c in range(n_cols):
        # Primary: use the strict first-row cell
        header_top = grid.row_positions[0]
        header_bottom = grid.row_positions[min(header_row_count, len(grid.row_positions) - 1)]
        header_cell = fitz.Rect(
            grid.col_positions[c], header_top,
            grid.col_positions[c + 1], header_bottom,
        )
        raw_header = extract_cell_text(page, header_cell).strip()

        # Fallback: if empty, expand vertically into the second row
        # This handles narrow header bands where text overflows the
        # first row cell boundary (e.g. Weight Schedule's "Volume" / "Weight")
        if not raw_header and len(grid.row_positions) > 2:
            expanded = fitz.Rect(
                grid.col_positions[c], header_top - 3,
                grid.col_positions[c + 1],
                grid.row_positions[min(2, len(grid.row_positions) - 1)],
            )
            raw_header = extract_cell_text(page, expanded).strip()

        canonical = normalize_header(raw_header)
        headers.append({
            "col_index": c,
            "raw_header": raw_header,
            "canonical_field": canonical,
            "parent_header": None,
        })

    return headers


# ---------------------------------------------------------------------------
# Table assembly
# ---------------------------------------------------------------------------

def _estimate_text_region(
    anchor: ScheduleAnchor,
    page_rect: fitz.Rect,
) -> fitz.Rect:
    """
    Estimates a search region for text-only tables based on the anchor
    title position. Used as a fallback when no vector ruling lines are
    found near the anchor.

    The estimated table width is derived from the anchor title width,
    centered on the anchor's position. The vertical extent starts just
    below the title and extends down by HARD_SEARCH_CAP.
    """
    anchor_w = anchor.bbox.x1 - anchor.bbox.x0
    margin_left = max(anchor_w * TEXT_FALLBACK_LEFT_MARGIN, TEXT_FALLBACK_MIN_MARGIN)
    margin_right = max(anchor_w * TEXT_FALLBACK_RIGHT_MARGIN, TEXT_FALLBACK_MIN_MARGIN)

    return fitz.Rect(
        max(page_rect.x0, anchor.bbox.x0 - margin_left),
        max(page_rect.y0, anchor.bbox.y1),
        min(page_rect.x1, anchor.bbox.x1 + margin_right),
        min(page_rect.y1, anchor.bbox.y1 + HARD_SEARCH_CAP),
    )


def build_table_from_anchor(
    page: fitz.Page,
    anchor: ScheduleAnchor,
    page_rect: fitz.Rect,
) -> dict | None:
    """
    Builds a complete table dict from a single anchor:
      1. Discover the table's actual x-bounds from nearby rulings
      2. Extract all grid lines within those bounds
      3. Refine the bottom edge (MAX_ROW_GAP)
      4. Build grid, extract headers, populate cells

    Uses two strategies in order:
      A) Vector grid reconstruction (primary) — requires horizontal and
         vertical ruling lines in the table area.
      B) Text clustering (fallback) — uses word positions to infer
         rows/columns when no vector lines exist (benchmark PDF's
         Insert / Dowel Bar schedules) or the grid has no data rows
         (Weight Schedule).
    """
    # --- Pass 1: discover the table's true boundary ---
    search_region = _discover_table_bounds(page, anchor, page_rect)

    # If no vector lines found, or the region is too narrow to be a real
    # table (e.g. drawing detail elements), fall back to text-only
    # estimation from the anchor position.
    use_text_only = False
    if search_region is None:
        use_text_only = True
    elif search_region.x1 - search_region.x0 < MIN_REGION_WIDTH:
        use_text_only = True

    if use_text_only:
        search_region = _estimate_text_region(anchor, page_rect)
        text_grid = build_text_grid(page, search_region)
        if text_grid is not None and len(text_grid.row_positions) >= 3:
            # Filter columns by proximity to anchor to prevent
            # cross-contamination from adjacent schedules.
            # Only keep columns whose midpoint is within
            # ANCHOR_PROXIMITY_MULTIPLIER × anchor_width of the
            # anchor center.
            grid = text_grid
            anchor_cx = (anchor.bbox.x0 + anchor.bbox.x1) / 2
            anchor_w = anchor.bbox.x1 - anchor.bbox.x0
            max_dist = anchor_w * ANCHOR_PROXIMITY_MULTIPLIER

            n_orig_cols = len(grid.col_positions) - 1
            keep = [False] * n_orig_cols
            for c in range(n_orig_cols):
                col_mid = (grid.col_positions[c] + grid.col_positions[c + 1]) / 2
                if abs(col_mid - anchor_cx) <= max_dist:
                    keep[c] = True

            if not any(keep):
                return None

            filtered_cols = [grid.col_positions[0]]
            for c in range(n_orig_cols):
                if keep[c]:
                    filtered_cols.append(grid.col_positions[c + 1])

            if len(filtered_cols) >= 3:
                # Rebuild grid with filtered columns
                n_cols_filtered = len(filtered_cols) - 1
                cells = build_cell_rects(grid.row_positions, filtered_cols)
                grid = TableGrid(
                    row_positions=grid.row_positions,
                    col_positions=filtered_cols,
                    cells=cells,
                )

            region = search_region
            lines = []
        else:
            return None
    else:
        # --- Pass 2: full extraction within discovered bounds ---
        raw_lines = extract_grid_lines(page, search_region)
        region, lines = refine_region_bottom(search_region, raw_lines)
        grid = build_grid(lines)

        if grid is None or len(grid.row_positions) < 3:
            # Grid found only header band (no data rows). Try
            # text clustering for the data rows.
            text_grid = build_text_grid(page, search_region)
            if text_grid is not None and len(text_grid.row_positions) >= 3:
                grid = text_grid
                raw_lines = extract_grid_lines(page, search_region)
                _, lines = refine_region_bottom(search_region, raw_lines)

        if grid is None or len(grid.row_positions) < 2 or len(grid.col_positions) < 2:
            return None

    detect_merged_header_cells(grid, lines, header_row_count=1)

    # Extract and normalize headers from the first row
    headers = _extract_headers(page, grid, header_row_count=1)

    # Build a set of column indices that contain rebar data
    rebar_col_indices = {
        h["col_index"] for h in headers
        if h["canonical_field"] in _REBAR_FIELDS
    }

    n_cols = len(grid.col_positions) - 1
    n_rows = len(grid.row_positions) - 1
    rows = []

    # Start from row 1 (skip header row)
    for r in range(1, n_rows):
        row_cells = []
        for c in range(n_cols):
            cell_rect = grid.cells[r * n_cols + c]
            raw_text = extract_cell_text(page, cell_rect)

            # Only parse rebar notation for columns identified as rebar fields
            normalized = None
            if c in rebar_col_indices:
                normalized = parse_rebar_value(raw_text)

            row_cells.append({
                "col_index": c,
                "raw_text": raw_text,
                "confidence": 1.0,
                "normalized_value": normalized,
                "bbox": [cell_rect.x0, cell_rect.y0, cell_rect.x1, cell_rect.y1],
            })
        rows.append({"row_index": r - 1, "cells": row_cells})

    return {
        "table_type": anchor.table_type,
        "title_raw": anchor.matched_text,
        "source_region_bbox": [region.x0, region.y0, region.x1, region.y1],
        "row_count": n_rows - 1,
        "col_count": n_cols,
        "header_row_index": 0,
        "headers": headers,
        "merged_header_cells": grid.merged_header_cells,
        "rows": rows,
    }


def extract_all_tables(pdf_path: str) -> list[dict]:
    """Entry point: opens a PDF, finds every schedule anchor on every
    page, and attempts to build a table for each one."""
    doc = fitz.open(pdf_path)
    tables = []
    for page_number, page in enumerate(doc, start=1):
        for anchor in find_schedule_anchors(page, page_number):
            table = build_table_from_anchor(page, anchor, page.rect)
            if table:
                table["page_number"] = page_number
                tables.append(table)
    return tables


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.tables.table_builder <path_to_pdf>")
        sys.exit(1)

    results = extract_all_tables(sys.argv[1])
    print(json.dumps(results, indent=2))
