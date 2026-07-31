"""
Tests for src.tables.text_clustering — validates row clustering,
cell clustering, column grid building, and the full text grid builder.

These are unit tests using synthetic word data (no PDF required).
"""

import pytest
import fitz
from dataclasses import dataclass

from src.tables.text_clustering import (
    TextRow,
    _cluster_rows, _cluster_cells_in_row,
    _build_column_grid, _get_all_words_in_row,
    CELL_GAP_THRESHOLD, ROW_TOLERANCE,
)


def _make_word(text, cx, cy, w=15, h=8):
    """Helper: create a synthetic word dict."""
    return {
        "text": text,
        "x0": cx - w / 2,
        "y0": cy - h / 2,
        "x1": cx + w / 2,
        "y1": cy + h / 2,
        "cx": cx,
        "cy": cy,
    }


class TestGetAllWordsInRow:
    """Tests for the safe word-flattening helper."""

    def test_unclustered_single_group(self):
        """Row.cells = [[w1, w2]] — single group, multiple words."""
        w1, w2 = _make_word("A", 10, 10), _make_word("B", 30, 10)
        row = TextRow(y_center=10, y0=6, y1=14, cells=[[w1, w2]])
        all_words = _get_all_words_in_row(row)
        assert len(all_words) == 2
        assert all_words[0]["text"] == "A"
        assert all_words[1]["text"] == "B"

    def test_clustered_multi_group(self):
        """Row.cells = [[w1], [w2]] — two cell groups."""
        w1, w2 = _make_word("A", 10, 10), _make_word("B", 60, 10)
        row = TextRow(y_center=10, y0=6, y1=14, cells=[[w1], [w2]])
        all_words = _get_all_words_in_row(row)
        assert len(all_words) == 2

    def test_empty_cells(self):
        row = TextRow(y_center=10, y0=6, y1=14, cells=[])
        assert _get_all_words_in_row(row) == []

    def test_single_word(self):
        w = _make_word("A", 10, 10)
        row = TextRow(y_center=10, y0=6, y1=14, cells=[[w]])
        all_words = _get_all_words_in_row(row)
        assert len(all_words) == 1
        assert all_words[0]["text"] == "A"


class TestClusterRows:

    def test_single_row(self):
        """Words at similar y → one row."""
        words = [
            _make_word("A", 10, 100),
            _make_word("B", 40, 101),
            _make_word("C", 70, 99),
        ]
        rows = _cluster_rows(words)
        assert len(rows) == 1
        assert len(rows[0].cells[0]) == 3

    def test_two_rows(self):
        """Words at distinctly different y → two rows."""
        words = [
            _make_word("H1", 10, 100),  # Header row
            _make_word("H2", 50, 100),
            _make_word("D1", 10, 120),  # Data row
            _make_word("D2", 50, 120),
        ]
        rows = _cluster_rows(words)
        assert len(rows) == 2
        assert rows[0].y_center < rows[1].y_center

    def test_three_rows(self):
        words = [
            _make_word("H1", 10, 100),
            _make_word("D1", 10, 120),
            _make_word("D2", 10, 140),
        ]
        rows = _cluster_rows(words)
        assert len(rows) == 3

    def test_empty_input(self):
        assert _cluster_rows([]) == []

    def test_y_tolerance_boundary(self):
        """Words just beyond ROW_TOLERANCE should be separate rows."""
        words = [
            _make_word("A", 10, 100),
            _make_word("B", 10, 100 + ROW_TOLERANCE + 1),
        ]
        rows = _cluster_rows(words)
        assert len(rows) == 2

    def test_words_sorted_by_y(self):
        """Words should be properly sorted regardless of input order."""
        words = [
            _make_word("C", 10, 130),
            _make_word("A", 10, 100),
            _make_word("B", 10, 115),
        ]
        rows = _cluster_rows(words)
        assert len(rows) >= 2  # A and B might be same row, C is separate
        assert rows[-1].y_center >= rows[0].y_center  # sorted by y


class TestClusterCellsInRow:

    def test_single_word(self):
        w = _make_word("Only", 50, 100)
        row = TextRow(y_center=100, y0=96, y1=104, cells=[[w]])
        groups = _cluster_cells_in_row(row)
        assert len(groups) == 1
        assert groups[0][0]["text"] == "Only"

    def test_two_separate_cells(self):
        """Words far apart → two cell groups."""
        w1 = _make_word("Left", 30, 100, w=20)
        w2 = _make_word("Right", 80, 100, w=20)
        # Gap: w2.x0(70) - w1.x1(40) = 30 > CELL_GAP_THRESHOLD → separate
        row = TextRow(y_center=100, y0=96, y1=104, cells=[[w1, w2]])
        groups = _cluster_cells_in_row(row)
        assert len(groups) == 2

    def test_adjacent_words_same_cell(self):
        """Words close together → one cell group."""
        w1 = _make_word("Ref", 50, 100, w=15)
        w2 = _make_word("No.", 68, 100, w=12)
        # Gap: w2.x0(62) - w1.x1(57.5) = 4.5 < CELL_GAP_THRESHOLD → same group
        row = TextRow(y_center=100, y0=96, y1=104, cells=[[w1, w2]])
        groups = _cluster_cells_in_row(row)
        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_three_cells_mixed_gaps(self):
        """Mixed: some close, some far."""
        w1 = _make_word("A", 20, 100, w=10)
        w2 = _make_word("B", 33, 100, w=10)   # gap ≈ 3 → same cell
        w3 = _make_word("C", 80, 100, w=10)
        # w3.x0(75) - w2.x1(38) = 37 > threshold → new cell
        row = TextRow(y_center=100, y0=96, y1=104, cells=[[w1, w2, w3]])
        groups = _cluster_cells_in_row(row)
        # Expect: [A, B] and [C]
        assert len(groups) == 2
        assert len(groups[0]) == 2
        assert len(groups[1]) == 1

    def test_gap_exactly_at_threshold(self):
        """Gap exactly at CELL_GAP_THRESHOLD → same cell."""
        w1 = _make_word("Left", 30, 100, w=20)
        w2 = _make_word("Right", 30 + 20 + CELL_GAP_THRESHOLD, 100, w=20)
        # Gap = CELL_GAP_THRESHOLD → gap > threshold? No, == not >
        row = TextRow(y_center=100, y0=96, y1=104, cells=[[w1, w2]])
        groups = _cluster_cells_in_row(row)
        # Exactly at threshold: gap > CELL_GAP_THRESHOLD is False → same group
        assert len(groups) == 1


class TestBuildColumnGrid:

    def test_simple_grid(self):
        """Two rows with consistent 2-column layout."""
        # Row 0 (header): two cells
        h1, h2 = _make_word("H1", 30, 100, w=20), _make_word("H2", 80, 100, w=20)
        row0 = TextRow(y_center=100, y0=96, y1=104, cells=[[h1, h2]])
        # Row 1 (data): two cells  
        d1, d2 = _make_word("D1", 30, 120, w=20), _make_word("D2", 80, 120, w=20)
        row1 = TextRow(y_center=120, y0=116, y1=124, cells=[[d1, d2]])

        col_positions = _build_column_grid([row0, row1])
        assert col_positions is not None
        assert len(col_positions) == 3  # left, divider, right

    def test_inconsistent_columns(self):
        """Rows with different column counts should still produce a result."""
        h1 = _make_word("H1", 30, 100, w=20)
        h2 = _make_word("H2", 80, 100, w=20)
        row0 = TextRow(y_center=100, y0=96, y1=104, cells=[[h1, h2]])

        # Data row has only 1 cell (content merged)
        d1 = _make_word("D1", 50, 120, w=40)
        row1 = TextRow(y_center=120, y0=116, y1=124, cells=[[d1]])

        col_positions = _build_column_grid([row0, row1])
        # Should fall back to header row's column positions
        assert col_positions is not None
        assert len(col_positions) == 3

    def test_empty_rows(self):
        assert _build_column_grid([]) is None

    def test_single_row(self):
        """Less than 2 groups → can't build columns."""
        w = _make_word("Only", 50, 100)
        row = TextRow(y_center=100, y0=96, y1=104, cells=[[w]])
        assert _build_column_grid([row]) is None

    def test_three_column_grid(self):
        """3 columns → 4 boundary positions."""
        row0 = TextRow(y_center=100, y0=96, y1=104, cells=[
            [_make_word("A", 20, 100, w=10)],
            [_make_word("B", 50, 100, w=10)],
            [_make_word("C", 80, 100, w=10)],
        ])
        row1 = TextRow(y_center=120, y0=116, y1=124, cells=[
            [_make_word("1", 20, 120, w=10)],
            [_make_word("2", 50, 120, w=10)],
            [_make_word("3", 80, 120, w=10)],
        ])
        col_positions = _build_column_grid([row0, row1])
        assert col_positions is not None
        assert len(col_positions) == 4  # 3 columns = 4 boundaries
