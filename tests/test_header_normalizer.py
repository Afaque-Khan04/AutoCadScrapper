"""
Tests for src.tables.header_normalizer — validates fuzzy header
matching against the alias dictionary.
"""

import pytest

# pyrefly: ignore [missing-import]
from src.tables.header_normalizer import normalize_header, normalize_headers_for_table


class TestNormalizeHeader:

    def test_exact_match(self):
        assert normalize_header("beam mark") == "beam_mark"
        assert normalize_header("beam size") == "beam_size"

    def test_case_insensitive(self):
        assert normalize_header("BEAM MARK") == "beam_mark"
        assert normalize_header("Beam Mark") == "beam_mark"

    def test_with_trailing_dot(self):
        """Common drafter notation: 'Beam Mkd.'"""
        assert normalize_header("Beam Mkd.") == "beam_mark"

    def test_bottom_reinforcement_typo(self):
        """Real-world typo from benchmark: 'BOTTAM REINFO.'"""
        assert normalize_header("BOTTAM REINFO.") == "bottom_reinforcement"

    def test_stirrups(self):
        assert normalize_header("Stirrups") == "stirrups"
        assert normalize_header("STIRRUPS") == "stirrups"

    def test_precast_fields(self):
        """Benchmark PDF headers."""
        assert normalize_header("Ref No.") == "ref_no"
        assert normalize_header("Type") == "type"
        assert normalize_header("Count") == "count"
        assert normalize_header("Bar Diameter") == "bar_diameter"
        assert normalize_header("Volume") == "volume"
        assert normalize_header("Weight") == "weight"

    def test_returns_none_for_unknown(self):
        assert normalize_header("xyzzy") is None
        assert normalize_header("") is None
        assert normalize_header("   ") is None

    def test_abbreviation_matching(self):
        """Short forms should fuzzy-match."""
        result = normalize_header("Dia")
        assert result == "bar_diameter"

    def test_remarks(self):
        assert normalize_header("Remarks") == "remarks"
        assert normalize_header("REMARKS") == "remarks"


class TestNormalizeHeadersForTable:

    def test_basic_list(self):
        raw = ["Ref No.", "Type", "Count"]
        result = normalize_headers_for_table(raw)

        assert len(result) == 3
        assert result[0]["canonical_field"] == "ref_no"
        assert result[1]["canonical_field"] == "type"
        assert result[2]["canonical_field"] == "count"
        assert all(r["parent_header"] is None for r in result)

    def test_preserves_raw_header(self):
        raw = ["BEAM MKD.", "BOTTAM REINFO."]
        result = normalize_headers_for_table(raw)

        assert result[0]["raw_header"] == "BEAM MKD."
        assert result[1]["raw_header"] == "BOTTAM REINFO."

    def test_col_indices_are_correct(self):
        raw = ["A", "B", "C"]
        result = normalize_headers_for_table(raw)
        assert [r["col_index"] for r in result] == [0, 1, 2]
