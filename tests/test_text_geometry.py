"""
Tests for src.tables.text_geometry — the shared row-clustering and
gap-based split utilities used by both text_clustering.py and
notes_parser.py.
"""

import pytest

from src.tables.text_geometry import cluster_words_into_rows, split_by_largest_gap


def _make_word(text, cx, cy, w=15, h=8):
    """Helper: create a synthetic word dict (same shape as the pipeline's)."""
    return {
        "text": text,
        "x0": cx - w / 2,
        "y0": cy - h / 2,
        "x1": cx + w / 2,
        "y1": cy + h / 2,
        "cx": cx,
        "cy": cy,
    }


class TestClusterWordsIntoRows:
    def test_empty_input(self):
        assert cluster_words_into_rows([], 6.0) == []

    def test_single_row(self):
        words = [
            _make_word("A", 10, 100),
            _make_word("B", 40, 101),
            _make_word("C", 70, 99),
        ]
        rows = cluster_words_into_rows(words, 6.0)
        assert len(rows) == 1
        assert len(rows[0]["words"]) == 3

    def test_two_rows(self):
        words = [
            _make_word("H1", 10, 100),
            _make_word("H2", 50, 100),
            _make_word("D1", 10, 120),
            _make_word("D2", 50, 120),
        ]
        rows = cluster_words_into_rows(words, 6.0)
        assert len(rows) == 2
        assert rows[0]["cy"] < rows[1]["cy"]

    def test_sorted_by_y_regardless_of_input_order(self):
        words = [
            _make_word("C", 10, 130),
            _make_word("A", 10, 100),
            _make_word("B", 10, 115),
        ]
        rows = cluster_words_into_rows(words, 6.0)
        assert len(rows) >= 2
        assert rows[-1]["cy"] >= rows[0]["cy"]

    def test_tolerance_boundary(self):
        """Words just beyond tolerance → separate rows."""
        words = [
            _make_word("A", 10, 100),
            _make_word("B", 10, 107),  # 100 + 6 + 1
        ]
        rows = cluster_words_into_rows(words, 6.0)
        assert len(rows) == 2

    def test_returns_word_objects_unchanged(self):
        words = [_make_word("A", 10, 100)]
        rows = cluster_words_into_rows(words, 6.0)
        assert rows[0]["words"][0] is words[0]


class TestSplitByLargestGap:
    def test_empty_input(self):
        left, right = split_by_largest_gap([], axis="x")
        assert left == []
        assert right == []

    def test_single_word(self):
        w = _make_word("Only", 50, 100)
        left, right = split_by_largest_gap([w], axis="x")
        assert left == [w]
        assert right == []

    def test_splits_at_largest_x_gap(self):
        """Key block, wide gap, value block → split between them."""
        words = [
            _make_word("KEY1", 10, 100, w=12),
            _make_word("KEY2", 25, 100, w=12),   # small gap from KEY1
            _make_word("VAL", 90, 100, w=12),     # large gap from KEY2
        ]
        left, right = split_by_largest_gap(words, axis="x")
        assert [w["text"] for w in left] == ["KEY1", "KEY2"]
        assert [w["text"] for w in right] == ["VAL"]

    def test_gap_uses_word_extents_not_centers(self):
        """Overlapping extents produce non-positive gaps that are never chosen."""
        words = [
            _make_word("A", 50, 100, w=40),   # x0=30, x1=70
            _make_word("B", 60, 100, w=40),   # x0=40, x1=80 → negative gap vs A
            _make_word("C", 140, 100, w=20),  # x0=130 → big positive gap vs B
        ]
        left, right = split_by_largest_gap(words, axis="x")
        assert [w["text"] for w in left] == ["A", "B"]
        assert [w["text"] for w in right] == ["C"]

    def test_y_axis_split(self):
        words = [
            _make_word("T1", 100, 10, h=10),
            _make_word("T2", 100, 13, h=10),
            _make_word("BOT", 100, 90, h=10),
        ]
        left, right = split_by_largest_gap(words, axis="y")
        assert [w["text"] for w in left] == ["T1", "T2"]
        assert [w["text"] for w in right] == ["BOT"]
