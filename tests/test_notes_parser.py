"""
Unit and integration tests for src.parsing.notes_parser.
"""

from pathlib import Path
import fitz
import pytest

# pyrefly: ignore [missing-import]
from src.parsing.notes_parser import normalize_key, parse_notes_region
# pyrefly: ignore [missing-import]
from src.tables.anchor_detection import find_schedule_anchors, ScheduleAnchor


BENCHMARK_PDF = Path("reference/benchmarkpdf.pdf")


class TestNormalizeKey:
    def test_basic(self):
        assert normalize_key("GRADE OF CONCRETE") == "grade_of_concrete"

    def test_punctuation(self):
        assert normalize_key("LIFTING,TRANSPORTATION AND ERECTION") == "liftingtransportation_and_erection"

    def test_whitespace(self):
        assert normalize_key("  COVER:  ") == "cover"


class TestNotesParserIntegration:
    @pytest.fixture(autouse=True)
    def setup_pdf(self):
        if not BENCHMARK_PDF.exists():
            pytest.skip("benchmarkpdf.pdf not found in reference/")
        self.doc = fitz.open(BENCHMARK_PDF)
        self.page = self.doc[0]

    def test_finds_general_notes_anchor(self):
        anchors = find_schedule_anchors(self.page, 1, include_notes=True)
        notes_anchors = [a for a in anchors if a.region_type == "general_notes"]
        assert len(notes_anchors) >= 1
        assert notes_anchors[0].table_type == "general_notes"

    def test_parses_general_notes_benchmark(self):
        anchors = find_schedule_anchors(self.page, 1, include_notes=True)
        notes_anchor = [a for a in anchors if a.region_type == "general_notes"][0]
        parsed = parse_notes_region(self.page, notes_anchor, self.page.rect)

        assert parsed["region_type"] == "general_notes"
        notes = parsed["general_notes"]

        # Check key-value items
        assert notes.get("grade_of_concrete") == "M50"
        assert notes.get("grade_of_steel") == "Fe500"
        assert notes.get("stripping_strength") == "M25"
        assert notes.get("liftingtransportation_and_erection") == "M35"

        # Check nested subsections
        assert "cover" in notes
        assert notes["cover"].get("column") == "40mm"

        # Check metadata — the standalone dimensions note must land in
        # metadata via the generic no-dash path, not as an empty-value key
        assert any("ALL DIMENSIONS" in m for m in parsed["metadata"])
        assert "all_dimensions_are_in_mm" not in notes
        assert not any(
            isinstance(v, str) and v == "" for v in notes.values()
        ), "dash-less standalone notes should not become empty-value keys"

    def test_excludes_client_block(self):
        anchors = find_schedule_anchors(self.page, 1, include_notes=True)
        notes_anchor = [a for a in anchors if a.region_type == "general_notes"][0]
        parsed = parse_notes_region(self.page, notes_anchor, self.page.rect)

        # Confirm CLIENT, SIFY BANGALORE, EXCEL PRECAST, etc. are NOT in the parsed notes
        raw_text_extracted = str(parsed).lower()
        assert "sify bangalore" not in raw_text_extracted
        assert "excel precast" not in raw_text_extracted
        assert "structural consultant" not in raw_text_extracted
