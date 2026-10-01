import sys
from pathlib import Path

# Add project root to sys.path so 'src' imports work regardless of CWD or invocation method
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import json
# pyrefly: ignore [missing-import]
import pytest
# pyrefly: ignore [missing-import]
from src.exporters.presentation_exporter import (
    simplify_for_presentation,
    export_presentation_json,
    _humanize,
)
# pyrefly: ignore [missing-import]
from src.tables.table_builder import extract_all_regions


BENCHMARK_PDF = PROJECT_ROOT / "reference" / "benchmarkpdf.pdf"


class TestPresentationExporterUnit:
    """Unit tests using synthetic table dicts."""

    def test_humanize(self):
        assert _humanize("grade_of_concrete") == "Grade Of Concrete"
        assert _humanize("cover") == "Cover"
        assert _humanize("beam_mark") == "Beam Mark"

    def test_simplify_general_notes(self):
        sample_notes = {
            "table_type": "general_notes",
            "title_raw": "GENERAL NOTES:\nGENERAL NOTES:",
            "general_notes": {
                "grade_of_concrete": "M50",
                "cover": {"column": "40mm"},
            },
            "legends": {
                "erection_mark": "",
            },
            "metadata": [
                "ALL DIMENSIONS ARE IN MM",
            ],
        }

        result = simplify_for_presentation([sample_notes])
        assert len(result["tables"]) == 1
        table = result["tables"][0]
        assert table["name"] == "GENERAL NOTES"
        assert table["type"] == "general_notes"
        assert table["notes"]["Grade Of Concrete"] == "M50"
        assert table["Cover"]["Column"] == "40mm"
        assert table["additional_notes"] == ["All dimensions are in mm"]
        assert table["legends"]["Erection Mark"] is None
        assert any("Erection Mark" in flag for flag in table["flags"])

    def test_simplify_schedule_table(self):
        sample_schedule = {
            "table_type": "insert_schedule",
            "title_raw": "Insert Schedule",
            "headers": [
                {"col_index": 0, "raw_header": "Ref No."},
                {"col_index": 1, "raw_header": "Type"},
                {"col_index": 2, "raw_header": "Count"},
            ],
            "rows": [
                {
                    "cells": [
                        {"col_index": 0, "raw_text": "N1"},
                        {"col_index": 1, "raw_text": "12.9Ø- LIFTING"},
                        {"col_index": 2, "raw_text": "2"},
                    ]
                }
            ],
        }

        result = simplify_for_presentation([sample_schedule])
        assert len(result["tables"]) == 1
        table = result["tables"][0]
        assert table["name"] == "Insert Schedule"
        assert table["type"] == "insert_schedule"
        assert table["rows"] == [
            {"Ref No.": "N1", "Type": "12.9Ø- LIFTING", "Count": "2"}
        ]


class TestPresentationExporterIntegration:
    """Integration tests against benchmark PDF."""

    def test_end_to_end_presentation_export(self, tmp_path):
        if not BENCHMARK_PDF.exists():
            pytest.skip("benchmarkpdf.pdf not found in reference/")

        regions = extract_all_regions(str(BENCHMARK_PDF))
        presentation = simplify_for_presentation(regions)

        assert "tables" in presentation
        assert len(presentation["tables"]) == 4

        types = [t["type"] for t in presentation["tables"]]
        assert "general_notes" in types
        assert "weight_schedule" in types
        assert "insert_schedule" in types
        assert "dowel_bar_schedule" in types

        # Check export to file
        out_file = tmp_path / "simplified.json"
        export_presentation_json(regions, output_path=out_file)
        assert out_file.exists()
        loaded = json.loads(out_file.read_text(encoding="utf-8"))
        assert loaded == presentation


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
