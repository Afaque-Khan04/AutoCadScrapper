"""
Text-clustering fallback for schedule tables that lack vector ruling
lines (the "Option B" strategy).

Some CAD-exported PDFs place schedule tables as pure text blocks without
any ruling lines — the table structure exists only in the spatial
arrangement of text on the page. This module recovers that structure by
clustering word positions into rows and columns.

Algorithm:
  1. Collect all word bounding boxes within the search region.
  2. Cluster words into rows by y-coordinate proximity.
  3. Within each row, cluster words into cells by x-coordinate proximity
     using a gap threshold — when the gap between consecutive words
     exceeds a threshold, a new cell boundary is inferred.
  4. Align cell boundaries across all rows to build a consistent column
     grid.
  5. Return a pseudo-TableGrid (same interface as grid_reconstructor)
     so the downstream pipeline (header_normalizer, rebar parser, etc.)
     can process it identically.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

import fitz

from .grid_reconstructor import TableGrid, build_cell_rects


# Minimum gap (in points) between two words to consider them in
# different columns. Derived from typical CAD text spacing where
# adjacent words in the same cell have 2-5pt gaps and cell-to-cell
# gaps are 10+ pts. Set at 8.0 to balance between keeping
# multi-word cells together and splitting adjacent columns.
CELL_GAP_THRESHOLD = 8.0

# Maximum y-difference (in points) for two words to be considered
# part of the same text row. Based on typical 3-5mm text height
# (~8-14pt font) found in engineering drawings.
ROW_TOLERANCE = 6.0

# Minimum number of words required to form a table. Below this, the
# region is probably just labels or scattered notes.
MIN_WORDS_FOR_TABLE = 6

# Minimum number of rows (including header) for a valid table.
MIN_ROWS = 2


@dataclass
class TextRow:
    """A row of word clusters (cell groups) detected from text positions."""
    y_center: float
    y0: float
    y1: float
    # Initially a single list of ALL words in the row: [w1, w2, w3, ...]
    # After cell clustering: [[cell0_words], [cell1_words], ...]
    cells: list[list[dict]] = field(default_factory=list)


def _collect_words_in_region(page: fitz.Page, region: fitz.Rect) -> list[dict]:
    """
    Returns all word dicts from page whose centers fall within `region`.
    Each dict: {'text': str, 'x0': float, 'y0': float, 'x1': float, 'y1': float,
                'cx': float, 'cy': float}
    """
    words = page.get_text("words")  # (x0, y0, x1, y1, word, block_no, line_no, word_no)
    result = []
    for w in words:
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        if region.x0 <= cx <= region.x1 and region.y0 <= cy <= region.y1:
            result.append({
                "text": w[4],
                "x0": w[0], "y0": w[1], "x1": w[2], "y1": w[3],
                "cx": cx, "cy": cy,
            })
    return result


def _get_all_words_in_row(row: TextRow) -> list[dict]:
    """
    Returns the flat list of all word dicts in this row, regardless of
    whether cells has been clustered ([[group], [group]]) or not ([[all_words]]).

    Distinguishes the two states by length:
      - Exactly 1 group AND first element is a dict → unclustered [[w1, w2, ...]]
      - Multiple groups → clustered [[cell0], [cell1], ...]
    """
    if not row.cells:
        return []
    # Unclustered: exactly one group with word dicts
    if len(row.cells) == 1 and row.cells[0] and isinstance(row.cells[0][0], dict):
        return row.cells[0]
    # Clustered: flatten all groups
    flat = []
    for group in row.cells:
        flat.extend(group)
    return flat


def _cluster_rows(words: list[dict]) -> list[TextRow]:
    """
    Groups words into rows by y-center proximity.

    Sorts words by cy, then clusters consecutive words whose cy values
    differ by at most ROW_TOLERANCE.
    """
    if not words:
        return []

    sorted_words = sorted(words, key=lambda w: w["cy"])
    rows: list[TextRow] = []
    current_cluster = [sorted_words[0]]
    current_cy = sorted_words[0]["cy"]

    for w in sorted_words[1:]:
        if abs(w["cy"] - current_cy) <= ROW_TOLERANCE:
            current_cluster.append(w)
            # Running average for y-center (avoids drift from repeated averaging)
            current_cy = (current_cy * (len(current_cluster) - 1) + w["cy"]) / len(current_cluster)
        else:
            # Finalize previous row
            y0 = min(c["y0"] for c in current_cluster)
            y1 = max(c["y1"] for c in current_cluster)
            rows.append(TextRow(
                y_center=current_cy,
                y0=y0,
                y1=y1,
                cells=[current_cluster],
            ))
            current_cluster = [w]
            current_cy = w["cy"]

    # Finalize last row
    if current_cluster:
        y0 = min(c["y0"] for c in current_cluster)
        y1 = max(c["y1"] for c in current_cluster)
        rows.append(TextRow(
            y_center=current_cy,
            y0=y0,
            y1=y1,
            cells=[current_cluster],
        ))

    return rows


def _cluster_cells_in_row(row: TextRow) -> list[list[dict]]:
    """
    Within a single row, groups its words into cell clusters based on
    x-gaps. When the horizontal gap between two consecutive words
    exceeds CELL_GAP_THRESHOLD, a new cell boundary is inserted.

    Always operates on the flat word list (row.cells[0] or flattened
    if already clustered), then returns the clustered result.
    """
    all_words = _get_all_words_in_row(row)
    sorted_words = sorted(all_words, key=lambda w: w["cx"])
    if len(sorted_words) <= 1:
        return [sorted_words]

    groups: list[list[dict]] = [[sorted_words[0]]]
    for w in sorted_words[1:]:
        prev = groups[-1][-1]
        gap = w["x0"] - prev["x1"]
        if gap > CELL_GAP_THRESHOLD:
            groups.append([w])
        else:
            groups[-1].append(w)

    return groups


def _build_column_grid(rows: list[TextRow]) -> list[float] | None:
    """
    Aligns cell boundaries across all rows to build a consistent set of
    column x-positions for the table.

    Strategy: Collect cell boundary positions from each row, then find
    the row with the most columns and average boundaries across matching
    rows. Returns sorted list of column x-positions (left edge, dividers,
    right edge), or None if alignment fails.
    """
    if not rows:
        return None

    # For each row, compute cell boundary positions
    all_boundaries: list[list[float]] = []
    for row in rows:
        groups = _cluster_cells_in_row(row)
        if len(groups) < 2:
            continue
        boundaries = []
        for group in groups:
            boundaries.append(min(w["x0"] for w in group))
        # Add the right edge of the last group
        boundaries.append(max(w["x1"] for w in groups[-1]))
        all_boundaries.append(boundaries)

    if not all_boundaries:
        return None

    # Use the row with the most columns as the reference
    ref_boundaries = max(all_boundaries, key=lambda b: len(b))

    # Average all boundary sets that have similar column counts
    # (within 1) to get stable positions
    ref_col_count = len(ref_boundaries)
    matching = [b for b in all_boundaries if abs(len(b) - ref_col_count) <= 1]

    if not matching:
        matching = [ref_boundaries]

    # Average the column positions
    n_cols = max(len(b) for b in matching)
    avg_boundaries = []
    for c in range(n_cols):
        vals = [b[c] for b in matching if c < len(b)]
        if vals:
            avg_boundaries.append(sum(vals) / len(vals))

    # Sort and return — need at least 3 boundaries for a valid 2-column table
    return sorted(avg_boundaries) if len(avg_boundaries) >= 3 else None


def build_text_grid(page: fitz.Page, region: fitz.Rect) -> Any | None:
    """
    Constructs a pseudo-TableGrid from text positions when no vector
    ruling lines are available.

    The returned object quacks like grid_reconstructor.TableGrid —
    it has row_positions, col_positions, and cells attributes — so the
    downstream pipeline can process it without modification.

    Returns None if not enough structure was found.
    """
    words = _collect_words_in_region(page, region)
    if len(words) < MIN_WORDS_FOR_TABLE:
        return None

    rows = _cluster_rows(words)
    if len(rows) < MIN_ROWS:
        return None

    # Build column grid (internally calls _cluster_cells_in_row on each row)
    col_positions = _build_column_grid(rows)
    if col_positions is None or len(col_positions) < 3:
        return None

    # Build row positions from text row y-bounds
    # We need len(rows)+1 positions to define len(rows) grid rows
    row_positions = [rows[0].y0]
    for i in range(len(rows) - 1):
        # Boundary between row i and i+1 = midpoint of the gap
        boundary = (rows[i].y1 + rows[i + 1].y0) / 2
        row_positions.append(boundary)
    row_positions.append(rows[-1].y1)

    if len(row_positions) < 3:
        return None

    cells = build_cell_rects(row_positions, col_positions)
    return TableGrid(
        row_positions=row_positions,
        col_positions=col_positions,
        cells=cells,
    )
