"""
Integration test: runs the full pipeline against the benchmark PDF
(reference/benchmarkpdf.pdf) and validates the output structure.

This is the key Phase 1 validation — if this passes, the core
vector extraction pipeline is working end-to-end.
"""

import json
import os
import pytest
from pathlib import Path

from src.tables.table_builder import extract_all_tables


BENCHMARK_PDF = Path(__file__).parent.parent / "reference" / "benchmarkpdf.pdf"


@pytest.fixture
def benchmark_tables():
    """Run the full pipeline once and cache results for all tests."""
    if not BENCHMARK_PDF.exists():
        pytest.skip(f"Benchmark PDF not found: {BENCHMARK_PDF}")
    return extract_all_tables(str(BENCHMARK_PDF))


class TestBenchmarkExtraction:
    """End-to-end tests against the benchmark PDF."""

    def test_tables_found(self, benchmark_tables):
        """Should find at least one schedule table."""
        assert len(benchmark_tables) > 0, (
            "No tables extracted — anchor detection or grid reconstruction "
            "may be failing against the real PDF."
        )

    def test_table_types_detected(self, benchmark_tables):
        """Benchmark PDF contains Weight, Insert, and Dowel Bar schedules."""
        found_types = {t["table_type"] for t in benchmark_tables}
        # We expect at least some of these — the exact set depends on
        # whether all three have detectable grids
        expected = {"weight_schedule", "insert_schedule", "dowel_bar_schedule"}
        overlap = found_types & expected
        assert len(overlap) > 0, (
            f"None of the expected schedule types found. "
            f"Detected types: {found_types}"
        )

    def test_table_structure(self, benchmark_tables):
        """Every extracted table should have the required schema fields."""
        required_keys = {
            "table_type", "title_raw", "source_region_bbox",
            "row_count", "col_count", "header_row_index",
            "headers", "rows", "page_number",
        }
        for table in benchmark_tables:
            missing = required_keys - set(table.keys())
            assert not missing, (
                f"Table '{table.get('title_raw', '?')}' is missing fields: {missing}"
            )

    def test_rows_have_cells(self, benchmark_tables):
        """Every data row should have cells with required fields."""
        cell_keys = {"col_index", "raw_text", "confidence", "normalized_value", "bbox"}
        for table in benchmark_tables:
            for row in table["rows"]:
                assert "cells" in row
                for cell in row["cells"]:
                    missing = cell_keys - set(cell.keys())
                    assert not missing, (
                        f"Cell in row {row['row_index']} is missing fields: {missing}"
                    )

    def test_headers_have_canonical_fields(self, benchmark_tables):
        """Headers should have raw_header and canonical_field."""
        for table in benchmark_tables:
            assert len(table["headers"]) > 0, (
                f"Table '{table['title_raw']}' has no headers"
            )
            for header in table["headers"]:
                assert "raw_header" in header
                assert "canonical_field" in header

    def test_page_numbers_are_positive(self, benchmark_tables):
        for table in benchmark_tables:
            assert table["page_number"] >= 1

    def test_revision_schedule_not_extracted(self, benchmark_tables):
        """REVISION SCHEDULE should be excluded."""
        for table in benchmark_tables:
            assert "revision" not in table["table_type"].lower()

    def test_confidence_is_1_for_vector(self, benchmark_tables):
        """Vector-extracted text should always have confidence 1.0."""
        for table in benchmark_tables:
            for row in table["rows"]:
                for cell in row["cells"]:
                    assert cell["confidence"] == 1.0

    def test_output_json_serializable(self, benchmark_tables):
        """The full output should be JSON-serializable."""
        json_str = json.dumps(benchmark_tables, indent=2)
        assert len(json_str) > 0
        # Round-trip check
        parsed = json.loads(json_str)
        assert len(parsed) == len(benchmark_tables)
