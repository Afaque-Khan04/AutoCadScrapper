"""
Tests for src.tables.grid_reconstructor — validates grid line
extraction, collinear merging, grid building, and merge detection.

These are unit tests using synthetic line data (no PDF required).
"""

import pytest
import fitz

# pyrefly: ignore [missing-import]
from src.tables.grid_reconstructor import (
    GridLine, TableGrid,
    _merge_collinear, _flatten_cluster,
    build_grid, detect_merged_header_cells,
)


class TestMergeCollinear:
    """Tests for broken/dashed segment merging."""

    def test_merges_close_horizontals(self):
        """Two horizontal lines at nearly the same y should merge."""
        lines = [
            GridLine("horizontal", 100.0, 50, 150),
            GridLine("horizontal", 100.5, 160, 250),  # same y (within tolerance)
        ]
        merged = _merge_collinear(lines)
        horiz = [l for l in merged if l.orientation == "horizontal"]
        assert len(horiz) == 1
        assert horiz[0].start == 50
        assert horiz[0].end == 250

    def test_keeps_distant_horizontals_separate(self):
        """Two horizontal lines far apart in y should NOT merge."""
        lines = [
            GridLine("horizontal", 100.0, 50, 250),
            GridLine("horizontal", 200.0, 50, 250),
        ]
        merged = _merge_collinear(lines)
        horiz = [l for l in merged if l.orientation == "horizontal"]
        assert len(horiz) == 2

    def test_merges_close_verticals(self):
        lines = [
            GridLine("vertical", 50.0, 100, 200),
            GridLine("vertical", 50.5, 210, 300),
        ]
        merged = _merge_collinear(lines)
        vert = [l for l in merged if l.orientation == "vertical"]
        assert len(vert) == 1
        assert vert[0].start == 100
        assert vert[0].end == 300

    def test_empty_input(self):
        assert _merge_collinear([]) == []


class TestBuildGrid:
    """Tests for grid construction from classified lines."""

    def _simple_3x3_lines(self) -> list[GridLine]:
        """A 3-column, 3-row grid (4 horizontal + 4 vertical lines)."""
        return [
            # Horizontal rulings
            GridLine("horizontal", 100, 50, 350),   # top
            GridLine("horizontal", 130, 50, 350),   # row 1-2
            GridLine("horizontal", 160, 50, 350),   # row 2-3
            GridLine("horizontal", 190, 50, 350),   # bottom
            # Vertical rulings
            GridLine("vertical", 50, 100, 190),      # left
            GridLine("vertical", 150, 100, 190),     # col 1-2
            GridLine("vertical", 250, 100, 190),     # col 2-3
            GridLine("vertical", 350, 100, 190),     # right
        ]

    def test_basic_grid(self):
        lines = self._simple_3x3_lines()
        grid = build_grid(lines)

        assert grid is not None
        assert len(grid.row_positions) == 4
        assert len(grid.col_positions) == 4
        assert len(grid.cells) == 9  # 3x3

    def test_returns_none_for_insufficient_lines(self):
        """Fewer than 2 rows or 2 cols → None."""
        lines = [GridLine("horizontal", 100, 50, 350)]
        assert build_grid(lines) is None

    def test_returns_none_for_only_vertical(self):
        lines = [
            GridLine("vertical", 50, 100, 200),
            GridLine("vertical", 150, 100, 200),
        ]
        assert build_grid(lines) is None

    def test_cell_rects_are_correct(self):
        lines = self._simple_3x3_lines()
        grid = build_grid(lines)
        assert grid is not None

        # First cell: top-left
        first = grid.cells[0]
        assert abs(first.x0 - 50) < 0.2
        assert abs(first.y0 - 100) < 0.2
        assert abs(first.x1 - 150) < 0.2
        assert abs(first.y1 - 130) < 0.2

    def test_vector_grid_is_labeled_vector(self):
        """Grids built from ruling lines must carry source="vector" so
        merge detection runs on them (see merge-gating regression test)."""
        lines = self._simple_3x3_lines()
        grid = build_grid(lines)
        assert grid is not None
        assert grid.source == "vector"

    def test_source_defaults_to_vector(self):
        """Dataclass default must be "vector" — text clustering tags its
        own output explicitly."""
        grid = TableGrid()
        assert grid.source == "vector"


class TestMergedHeaderDetection:

    def test_detects_horizontal_merge(self):
        """A vertical ruling exists in body but not in header → horizontal merge."""
        lines = [
            GridLine("horizontal", 100, 50, 350),   # header top
            GridLine("horizontal", 130, 50, 350),   # header bottom / body top
            GridLine("horizontal", 160, 50, 350),   # body row
            GridLine("vertical", 50, 100, 160),      # left (full height)
            GridLine("vertical", 200, 130, 160),     # mid — body only, NOT in header
            GridLine("vertical", 350, 100, 160),     # right (full height)
        ]
        grid = build_grid(lines)
        assert grid is not None

        detect_merged_header_cells(grid, lines, header_row_count=1)

        # Should detect that the mid-column vertical doesn't span the header
        h_merges = [m for m in grid.merged_header_cells if m["merge_type"] == "horizontal"]
        assert len(h_merges) >= 1

    def test_no_merges_when_all_verticals_span_header(self):
        """All verticals go through header → no horizontal merges."""
        lines = [
            GridLine("horizontal", 100, 50, 350),
            GridLine("horizontal", 130, 50, 350),
            GridLine("horizontal", 160, 50, 350),
            GridLine("vertical", 50, 100, 160),   # full span
            GridLine("vertical", 200, 100, 160),  # full span
            GridLine("vertical", 350, 100, 160),  # full span
        ]
        grid = build_grid(lines)
        assert grid is not None
        detect_merged_header_cells(grid, lines, header_row_count=1)
        assert len(grid.merged_header_cells) == 0
