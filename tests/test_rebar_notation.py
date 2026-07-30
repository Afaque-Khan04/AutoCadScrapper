"""
Tests for src.parsing.rebar_notation — validates all rebar shorthand
variants against expected structured output.

These tests are pure-logic (no PDF I/O) and should run fast.
"""

import pytest
from src.parsing.rebar_notation import parse_rebar_value, _parse_single_group


class TestParseSingleGroup:
    """Tests for individual rebar notation patterns."""

    def test_count_dash_bar_type(self):
        """Standard notation: 4-T20 -> count=4, bar_type=T20"""
        result = _parse_single_group("4-T20")
        assert result == {"count": 4, "bar_type": "T20"}

    def test_count_dash_bar_type_lowercase(self):
        """Case insensitivity: 4-t20 -> T20 (uppercased)"""
        result = _parse_single_group("4-t20")
        assert result == {"count": 4, "bar_type": "T20"}

    def test_count_dash_diameter_symbol(self):
        """Diameter symbol notation: 2-16\u00d8 -> count=2, diameter_mm=16"""
        result = _parse_single_group("2-16\u00d8")
        assert result == {"count": 2, "diameter_mm": 16}

    def test_count_dash_diameter_small_symbol(self):
        """Small diameter symbol: 3-12\u00f8 -> count=3, diameter_mm=12"""
        result = _parse_single_group("3-12\u00f8")
        assert result == {"count": 3, "diameter_mm": 12}

    def test_bar_type_at_spacing(self):
        """Spacing notation: T10@150c/c -> bar_type=T10, spacing_mm=150"""
        result = _parse_single_group("T10@150c/c")
        assert result == {"bar_type": "T10", "spacing_mm": 150}

    def test_bar_type_at_spacing_with_spaces(self):
        """Spacing with spaces: T10 @ 150 C / C"""
        result = _parse_single_group("T10 @ 150 C / C")
        assert result == {"bar_type": "T10", "spacing_mm": 150}

    def test_diameter_spacing_no_separator(self):
        """Stirrup style: 6\u00d8130C/C -> diameter_mm=6, spacing_mm=130"""
        result = _parse_single_group("6\u00d8130C/C")
        assert result == {"diameter_mm": 6, "spacing_mm": 130}

    def test_empty_string(self):
        assert _parse_single_group("") is None

    def test_whitespace_only(self):
        assert _parse_single_group("   ") is None

    def test_unrecognized_text(self):
        """Non-rebar text should return None."""
        assert _parse_single_group("B1") is None
        assert _parse_single_group("230x450") is None
        assert _parse_single_group("-") is None
        assert _parse_single_group("N/A") is None


class TestParseRebarValue:
    """Tests for the compound-aware top-level parser."""

    def test_single_group(self):
        """Single group wraps in a list."""
        result = parse_rebar_value("4-T20")
        assert result == [{"count": 4, "bar_type": "T20"}]

    def test_compound_two_groups(self):
        """Compound cell: 2-16\u00d8+1-12\u00d8 -> two separate groups."""
        result = parse_rebar_value("2-16\u00d8+1-12\u00d8")
        assert result == [
            {"count": 2, "diameter_mm": 16},
            {"count": 1, "diameter_mm": 12},
        ]

    def test_compound_three_groups(self):
        """Three groups joined by +."""
        result = parse_rebar_value("2-T16+1-T12+1-T10")
        assert result == [
            {"count": 2, "bar_type": "T16"},
            {"count": 1, "bar_type": "T12"},
            {"count": 1, "bar_type": "T10"},
        ]

    def test_spacing_notation(self):
        result = parse_rebar_value("T10@150c/c")
        assert result == [{"bar_type": "T10", "spacing_mm": 150}]

    def test_returns_none_for_empty(self):
        assert parse_rebar_value("") is None
        assert parse_rebar_value(None) is None

    def test_returns_none_for_non_rebar(self):
        """Non-rebar text should return None, not an empty list."""
        assert parse_rebar_value("B1") is None
        assert parse_rebar_value("General Notes") is None

    def test_compound_with_one_invalid(self):
        """If one group in a compound is unrecognized, still parse the valid one."""
        result = parse_rebar_value("4-T20+unknown")
        assert result == [{"count": 4, "bar_type": "T20"}]

    def test_all_groups_invalid(self):
        """If ALL groups are unrecognized, return None."""
        assert parse_rebar_value("abc+xyz") is None
