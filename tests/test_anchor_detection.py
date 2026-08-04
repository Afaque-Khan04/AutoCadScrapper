"""
Tests for src.tables.anchor_detection — validates schedule-title
keyword detection with mocked PyMuPDF page objects.
"""

import pytest
from unittest.mock import MagicMock, PropertyMock
import fitz

# pyrefly: ignore [missing-import]
from src.tables.anchor_detection import find_schedule_anchors


def _make_mock_page(blocks: list[tuple]) -> MagicMock:
    """
    Creates a mock fitz.Page that returns the given text blocks
    from get_text("blocks").

    Each block is a tuple: (x0, y0, x1, y1, text, block_no, block_type)
    block_type 0 = text, 1 = image.
    """
    page = MagicMock(spec=fitz.Page)
    page.get_text.return_value = blocks
    return page


class TestFindScheduleAnchors:

    def test_finds_beam_schedule(self):
        blocks = [
            (50, 100, 300, 120, "SCHEDULE OF BEAMS", 0, 0),
        ]
        page = _make_mock_page(blocks)
        anchors = find_schedule_anchors(page, page_number=1)

        assert len(anchors) == 1
        assert anchors[0].table_type == "beam_schedule"
        assert anchors[0].matched_text == "SCHEDULE OF BEAMS"
        assert anchors[0].page_number == 1

    def test_finds_slab_schedule_case_insensitive(self):
        blocks = [
            (50, 200, 300, 220, "Schedule of Slabs", 0, 0),
        ]
        page = _make_mock_page(blocks)
        anchors = find_schedule_anchors(page, page_number=2)

        assert len(anchors) == 1
        assert anchors[0].table_type == "slab_schedule"

    def test_finds_multiple_schedules_on_one_page(self):
        """The benchmark PDF has Weight, Insert, and Dowel Bar schedules."""
        blocks = [
            (62, 719, 137, 733, "Weight Schedule", 0, 0),
            (237, 719, 306, 733, "Insert Schedule", 1, 0),
            (408, 719, 498, 733, "Dowel Bar Schedule", 2, 0),
        ]
        page = _make_mock_page(blocks)
        anchors = find_schedule_anchors(page, page_number=1)

        assert len(anchors) == 3
        types = {a.table_type for a in anchors}
        assert types == {"weight_schedule", "insert_schedule", "dowel_bar_schedule"}

    def test_excludes_revision_schedule(self):
        """REVISION SCHEDULE in the title block should NOT be detected."""
        blocks = [
            (1020, 713, 1093, 725, "REVISION SCHEDULE", 0, 0),
            (62, 719, 137, 733, "Weight Schedule", 1, 0),
        ]
        page = _make_mock_page(blocks)
        anchors = find_schedule_anchors(page, page_number=1)

        assert len(anchors) == 1
        assert anchors[0].table_type == "weight_schedule"

    def test_skips_image_blocks(self):
        """block_type=1 (image) should be skipped entirely."""
        blocks = [
            (50, 100, 300, 120, "SCHEDULE OF BEAMS", 0, 1),  # image block
        ]
        page = _make_mock_page(blocks)
        anchors = find_schedule_anchors(page, page_number=1)
        assert len(anchors) == 0

    def test_handles_extra_whitespace(self):
        """Drafter put extra spaces: 'SCHEDULE   OF   BEAMS'"""
        blocks = [
            (50, 100, 300, 120, "SCHEDULE   OF   BEAMS", 0, 0),
        ]
        page = _make_mock_page(blocks)
        anchors = find_schedule_anchors(page, page_number=1)
        assert len(anchors) == 1
        assert anchors[0].table_type == "beam_schedule"

    def test_no_matches_returns_empty(self):
        blocks = [
            (50, 100, 300, 120, "GENERAL NOTES", 0, 0),
            (50, 200, 300, 220, "Some other text", 1, 0),
        ]
        page = _make_mock_page(blocks)
        anchors = find_schedule_anchors(page, page_number=1)
        assert len(anchors) == 0

    def test_bar_bending_schedule(self):
        blocks = [
            (50, 100, 300, 120, "BAR BENDING SCHEDULE", 0, 0),
        ]
        page = _make_mock_page(blocks)
        anchors = find_schedule_anchors(page, page_number=1)
        assert len(anchors) == 1
        assert anchors[0].table_type == "bar_bending_schedule"

    def test_bbs_abbreviation(self):
        blocks = [
            (50, 100, 80, 120, "BBS", 0, 0),
        ]
        page = _make_mock_page(blocks)
        anchors = find_schedule_anchors(page, page_number=1)
        assert len(anchors) == 1
        assert anchors[0].table_type == "bar_bending_schedule"

    def test_slab_beam_schedule(self):
        """'SCHEDULE OF SLAB BEAM(SB)' should match beam_schedule."""
        blocks = [
            (50, 100, 300, 120, "SCHEDULE OF SLAB BEAM(SB)", 0, 0),
        ]
        page = _make_mock_page(blocks)
        anchors = find_schedule_anchors(page, page_number=1)
        assert len(anchors) == 1
        assert anchors[0].table_type == "beam_schedule"

    def test_bbox_preserved(self):
        """Anchor bbox should match the block's coordinates."""
        blocks = [
            (62.5, 719.3, 137.2, 733.1, "Weight Schedule", 0, 0),
        ]
        page = _make_mock_page(blocks)
        anchors = find_schedule_anchors(page, page_number=1)
        bbox = anchors[0].bbox
        assert abs(bbox.x0 - 62.5) < 0.01
        assert abs(bbox.y0 - 719.3) < 0.01
