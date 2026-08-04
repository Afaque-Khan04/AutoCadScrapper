"""
Reconstructs a row/column grid from vector line geometry within a
candidate table region. This is the primary table-detection strategy
(Option A) for AutoCAD-exported vector PDFs: schedule tables in these
drawings are almost always drawn with real ruling lines, so recovering
the grid directly from vector paths is more reliable than any
text-position heuristic.

Falls back to `text_clustering.py` only when a usable grid cannot be
found in the region (e.g. fewer than 2 rows or 2 columns detected).
"""

from __future__ import annotations
from dataclasses import dataclass, field
import fitz

from ..detection.title_block_zone import BBox

ANGLE_TOLERANCE_DEG = 3.0         # unused directly (see dx/dy check) -- kept for documentation of intent
COLLINEAR_MERGE_TOLERANCE = 2.0   # pts; merges broken/dashed segments into one logical line
MIN_LINE_LENGTH = 5.0             # pts; filters out arrowhead-scale noise, tick marks, etc.
MAX_ROW_GAP = 40.0               # pts; gap > this between consecutive horizontals = end of table



@dataclass
class GridLine:
    orientation: str   # "horizontal" or "vertical"
    position: float     # y for horizontal, x for vertical
    start: float          # x0 for horizontal, y0 for vertical
    end: float            # x1 for horizontal, y1 for vertical


@dataclass
class TableGrid:
    row_positions: list[float] = field(default_factory=list)              # y-coords of horizontal rulings
    col_positions: list[float] = field(default_factory=list)              # x-coords of vertical rulings
    cells: list[fitz.Rect] = field(default_factory=list)                   # every reconstructed cell rect
    merged_header_cells: list[dict] = field(default_factory=list)        # [{"bbox": [...], "merge_type": "horizontal"|"vertical"}]
    # Which strategy built this grid: "vector" (ruling-line reconstruction)
    # or "text_clustering" (no vector lines available). Drives
    # merge-detection gating in table_builder so text-derived grids
    # never get spurious "merge_type" flags.
    source: str = "vector"


def extract_grid_lines(page: fitz.Page, region: fitz.Rect) -> list[GridLine]:
    """
    Pulls straight line segments from page.get_drawings() that fall
    within `region`, classifies them as horizontal or vertical, and
    discards anything at an angle (arrows, hatching, leaders -- none
    of which represent table rulings).
    """
    raw_lines: list[GridLine] = []

    for drawing in page.get_drawings():
        if not region.intersects(fitz.Rect(drawing["rect"])):
            continue
        for item in drawing["items"]:
            if item[0] != "l":  # only straight line segments; ignore curves/rects/quads here
                continue
            p1, p2 = item[1], item[2]
            dx, dy = abs(p2.x - p1.x), abs(p2.y - p1.y)
            length = (dx ** 2 + dy ** 2) ** 0.5
            if length < MIN_LINE_LENGTH:
                continue

            if dy < COLLINEAR_MERGE_TOLERANCE:  # horizontal ruling
                raw_lines.append(GridLine("horizontal", (p1.y + p2.y) / 2, min(p1.x, p2.x), max(p1.x, p2.x)))
            elif dx < COLLINEAR_MERGE_TOLERANCE:  # vertical ruling
                raw_lines.append(GridLine("vertical", (p1.x + p2.x) / 2, min(p1.y, p2.y), max(p1.y, p2.y)))
            # anything else is angled -- not a table ruling, discard

    return _merge_collinear(raw_lines)


def _merge_collinear(lines: list[GridLine]) -> list[GridLine]:
    """
    Merges broken/dashed segments that share (approximately) the same
    position into one logical ruling line spanning their combined
    start/end -- common when a ruling is drawn as several short
    polyline pieces rather than one continuous line.
    """
    merged: list[GridLine] = []
    for orientation in ("horizontal", "vertical"):
        group = sorted((l for l in lines if l.orientation == orientation), key=lambda l: l.position)
        cluster: list[GridLine] = []
        for line in group:
            if cluster and abs(line.position - cluster[-1].position) <= COLLINEAR_MERGE_TOLERANCE:
                cluster.append(line)
            else:
                if cluster:
                    merged.append(_flatten_cluster(cluster, orientation))
                cluster = [line]
        if cluster:
            merged.append(_flatten_cluster(cluster, orientation))
    return merged


def _flatten_cluster(cluster: list[GridLine], orientation: str) -> GridLine:
    avg_position = sum(l.position for l in cluster) / len(cluster)
    start = min(l.start for l in cluster)
    end = max(l.end for l in cluster)
    return GridLine(orientation, avg_position, start, end)


def build_cell_rects(
    row_positions: list[float],
    col_positions: list[float],
) -> list[fitz.Rect]:
    """
    Shared helper: builds a flat list of cell rectangles from grid
    row and column boundary positions. Used by both vector grid
    reconstruction and text clustering to avoid duplicating the
    nested loop logic.

    Returns one Rect per cell in row-major order:
       cells[r * n_cols + c] = rect for row r, column c
    """
    cells: list[fitz.Rect] = []
    for r in range(len(row_positions) - 1):
        for c in range(len(col_positions) - 1):
            cells.append(fitz.Rect(
                col_positions[c], row_positions[r],
                col_positions[c + 1], row_positions[r + 1],
            ))
    return cells


def build_grid(lines: list[GridLine]) -> TableGrid | None:
    """
    Turns classified/merged grid lines into row and column positions,
    then the resulting cell rectangles. Returns None if fewer than 2
    rows or 2 columns were found -- the caller should treat that as
    "no usable grid" and fall back to text clustering.
    """
    row_positions = sorted({round(l.position, 1) for l in lines if l.orientation == "horizontal"})
    col_positions = sorted({round(l.position, 1) for l in lines if l.orientation == "vertical"})

    if len(row_positions) < 2 or len(col_positions) < 2:
        return None

    cells = build_cell_rects(row_positions, col_positions)
    return TableGrid(row_positions=row_positions, col_positions=col_positions, cells=cells)


def detect_merged_header_cells(grid: TableGrid, lines: list[GridLine], header_row_count: int = 1) -> None:
    """
    Flags header cells that are merged in EITHER direction. Real
    schedule tables (see: Schedule of Beams) mix both in the same
    header:

    - Horizontal merge -- a parent label spanning multiple sub-columns
      (e.g. "BOTTAM REINFO." spanning "STR." / "BENT"): an interior
      vertical ruling exists in the body rows but does not extend up
      into the header band.

    - Vertical merge -- a column with no sub-columns at all, so its
      single header cell spans the full header height while its
      neighbors split into two rows (e.g. "BEAM MKD." next to
      "BOTTAM REINFO."): an interior horizontal ruling that separates
      header sub-rows for other columns is absent across this
      column's x-range.

    Mutates grid.merged_header_cells in place.
    """
    if len(grid.row_positions) <= header_row_count or header_row_count < 1:
        return

    header_top = grid.row_positions[0]
    header_bottom = grid.row_positions[header_row_count]

    # --- horizontal merges: column divider present in body, absent across the header band ---
    for i, col_x in enumerate(grid.col_positions[1:-1], start=1):
        matching = [
            l for l in lines
            if l.orientation == "vertical" and abs(l.position - col_x) <= COLLINEAR_MERGE_TOLERANCE
        ]
        spans_header = any(l.start <= header_top + 1 and l.end >= header_bottom - 1 for l in matching)
        if not spans_header:
            grid.merged_header_cells.append({
                "bbox": [grid.col_positions[i - 1], header_top, grid.col_positions[i + 1], header_bottom],
                "merge_type": "horizontal",
            })

    # --- vertical merges: header sub-row divider present under some columns, absent under others ---
    for row_y in grid.row_positions[1:header_row_count]:  # interior header dividers only
        horizontal_at_y = [
            l for l in lines
            if l.orientation == "horizontal" and abs(l.position - row_y) <= COLLINEAR_MERGE_TOLERANCE
        ]
        for c in range(len(grid.col_positions) - 1):
            col_left, col_right = grid.col_positions[c], grid.col_positions[c + 1]
            spans_column = any(
                l.start <= col_left + 1 and l.end >= col_right - 1
                for l in horizontal_at_y
            )
            if not spans_column:
                grid.merged_header_cells.append({
                    "bbox": [col_left, header_top, col_right, header_bottom],
                    "merge_type": "vertical",
                })


def extract_closed_rectangles(page: fitz.Page) -> list[BBox]:
    """
    Extracts bounding boxes of closed vector rectangles on the page.
    Used by title_block_zone detection to find title block frames without
    duplicate line parsing.
    """
    rects: list[BBox] = []
    for drawing in page.get_drawings():
        d_rect = fitz.Rect(drawing["rect"])
        if d_rect.width >= 20.0 and d_rect.height >= 20.0:
            rects.append(BBox(d_rect.x0, d_rect.y0, d_rect.x1, d_rect.y1))
    return rects


def refine_region_bottom(
    region: fitz.Rect,
    lines: list[GridLine],
) -> tuple[fitz.Rect, list[GridLine]]:
    """
    Trims the region's bottom edge to the end of the actual contiguous
    ruling block instead of trusting a fixed height.
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


