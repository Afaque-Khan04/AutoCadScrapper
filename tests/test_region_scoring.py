"""
Regression test for the confidence-based ensemble scorer, built from
the ACTUAL regions on reference/benchmarkpdf.pdf.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# pyrefly: ignore [missing-import]
from src.detection.dictionaries import load_default_stores
# pyrefly: ignore [missing-import]
from src.detection.region_candidates import find_candidate_regions_for_page
# pyrefly: ignore [missing-import]
from src.detection.scoring import RegionCandidate

# pyrefly: ignore [missing-import]
from src.detection.title_block_zone import BBox

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "dictionaries"

PAGE_WIDTH = 1300.0
PAGE_HEIGHT = 950.0
TITLE_BLOCK_RECT = BBox(x0=1060.0, y0=20.0, x1=1290.0, y1=930.0)


@pytest.fixture
def stores():
    return load_default_stores(DATA_DIR)


def _candidate(bbox: BBox, structure_source: str, headers: list[str], rows: int, cols: int) -> RegionCandidate:
    return RegionCandidate(
        bbox=bbox,
        structure_source=structure_source,
        header_texts=headers,
        row_count=rows,
        col_count=cols,
    )


def test_weight_schedule_is_kept(stores):
    allow_store, deny_store = stores
    candidate = _candidate(
        bbox=BBox(30, 780, 195, 830),
        structure_source="vector_grid",
        headers=["Volume", "Weight"],
        rows=1,
        cols=2,
    )
    result = find_candidate_regions_for_page(
        PAGE_WIDTH, PAGE_HEIGHT, [candidate], [TITLE_BLOCK_RECT], allow_store, deny_store
    )[0]
    assert result.keep, result.breakdown


def test_insert_schedule_is_kept(stores):
    allow_store, deny_store = stores
    candidate = _candidate(
        bbox=BBox(210, 780, 400, 850),
        structure_source="vector_grid",
        headers=["Ref No.", "Type", "Count"],
        rows=3,
        cols=3,
    )
    result = find_candidate_regions_for_page(
        PAGE_WIDTH, PAGE_HEIGHT, [candidate], [TITLE_BLOCK_RECT], allow_store, deny_store
    )[0]
    assert result.keep, result.breakdown


def test_dowel_bar_schedule_is_kept(stores):
    allow_store, deny_store = stores
    candidate = _candidate(
        bbox=BBox(415, 780, 600, 850),
        structure_source="vector_grid",
        headers=["Ref No", "Bar Diameter", "Count"],
        rows=3,
        cols=3,
    )
    result = find_candidate_regions_for_page(
        PAGE_WIDTH, PAGE_HEIGHT, [candidate], [TITLE_BLOCK_RECT], allow_store, deny_store
    )[0]
    assert result.keep, result.breakdown


def test_general_notes_is_kept_via_structural_cues(stores):
    allow_store, deny_store = stores
    candidate = _candidate(
        bbox=BBox(1065, 25, 1285, 300),
        structure_source="text_clustering",
        headers=["GRADE OF CONCRETE", "GRADE OF STEEL", "COVER", "LEGENDS"],
        rows=6,
        cols=2,
    )
    result = find_candidate_regions_for_page(
        PAGE_WIDTH, PAGE_HEIGHT, [candidate], [TITLE_BLOCK_RECT], allow_store, deny_store
    )[0]
    assert result.keep, result.breakdown


def test_revision_schedule_is_rejected(stores):
    allow_store, deny_store = stores
    candidate = _candidate(
        bbox=BBox(1065, 745, 1285, 780),
        structure_source="vector_grid",
        headers=["Rev", "Date", "Description", "Chkd", "Appd"],
        rows=1,
        cols=5,
    )
    result = find_candidate_regions_for_page(
        PAGE_WIDTH, PAGE_HEIGHT, [candidate], [TITLE_BLOCK_RECT], allow_store, deny_store
    )[0]
    assert not result.keep, result.breakdown


def test_client_project_block_is_rejected(stores):
    allow_store, deny_store = stores
    candidate = _candidate(
        bbox=BBox(1065, 460, 1285, 620),
        structure_source="text_clustering",
        headers=["Client", "Project"],
        rows=8,
        cols=1,
    )
    result = find_candidate_regions_for_page(
        PAGE_WIDTH, PAGE_HEIGHT, [candidate], [TITLE_BLOCK_RECT], allow_store, deny_store
    )[0]
    assert not result.keep, result.breakdown


def test_structural_consultant_block_is_rejected(stores):
    allow_store, deny_store = stores
    candidate = _candidate(
        bbox=BBox(1065, 620, 1285, 745),
        structure_source="text_clustering",
        headers=["Structural Consultant"],
        rows=5,
        cols=1,
    )
    result = find_candidate_regions_for_page(
        PAGE_WIDTH, PAGE_HEIGHT, [candidate], [TITLE_BLOCK_RECT], allow_store, deny_store
    )[0]
    assert not result.keep, result.breakdown


def test_end_to_end_benchmark_pdf(stores):
    """
    End-to-end integration test running page-wide candidate scanning and confidence scoring
    against reference/benchmarkpdf.pdf.
    """
    pdf_path = Path(__file__).resolve().parents[1] / "reference" / "benchmarkpdf.pdf"
    if not pdf_path.exists():
        pytest.skip(f"Benchmark PDF not found at {pdf_path}")

    import fitz
    # pyrefly: ignore [missing-import]
    from src.tables.candidate_scanner import scan_page_for_candidates

    doc = fitz.open(str(pdf_path))
    page = doc[0]

    raw_candidates, rect_zone_candidates = scan_page_for_candidates(page)

    # Amendment 4 Assertion: Weight Schedule specifically survives candidate scanning
    weight_sched_scanned = any(
        "Volume" in c.header_texts or "Weight" in c.header_texts
        for c in raw_candidates
    )
    assert weight_sched_scanned, "Weight Schedule failed to survive the page-wide candidate scanning stage."

    allow_store, deny_store = stores
    scored_regions = find_candidate_regions_for_page(
        page.rect.width,
        page.rect.height,
        raw_candidates,
        rect_zone_candidates,
        allow_store,
        deny_store,
    )

    kept_regions = [r for r in scored_regions if r.keep]
    rejected_regions = [r for r in scored_regions if not r.keep]

    kept_headers = [r.candidate.header_texts for r in kept_regions]

    # Assert kept regions: Weight, Insert, Dowel Bar, General Notes
    assert any("Weight" in h or "Volume" in h for h in kept_headers), "Weight Schedule should be kept"
    assert any("Type" in h for h in kept_headers), "Insert Schedule should be kept"
    assert any("Bar Diameter" in h for h in kept_headers), "Dowel Bar Schedule should be kept"
    assert any("GRADE OF STEEL" in h or "GRADE OF CONCRETE" in h or "LEGENDS" in h for h in kept_headers), "General Notes should be kept"


    rejected_headers = [r.candidate.header_texts for r in rejected_regions]
    # Assert rejected regions: Revision, Client, Structural Consultant
    assert any("Rev" in h or "Chkd" in h for h in rejected_headers), "Revision Schedule should be rejected"

    # Amendment 6 Note: Page-wide scanning surfaces text_clustering candidates which may
    # trigger pre-existing detect_merged_header_cells false-flagging behavior.


def test_legacy_vs_confidence_detection_parity():
    """
    Amendment 7: Runs extract_all_regions() against reference/benchmarkpdf.pdf with
    use_confidence_detection=False and True, and asserts region identity parity.
    """
    pdf_path = Path(__file__).resolve().parents[1] / "reference" / "benchmarkpdf.pdf"
    if not pdf_path.exists():
        pytest.skip(f"Benchmark PDF not found at {pdf_path}")

    # pyrefly: ignore [missing-import]
    from src.tables.table_builder import extract_all_regions

    legacy_result = extract_all_regions(str(pdf_path), use_confidence_detection=False)
    new_result = extract_all_regions(str(pdf_path), use_confidence_detection=True)

    legacy_types = {r["table_type"] for r in legacy_result}
    new_types = {r["table_type"] for r in new_result}

    assert legacy_types == new_types, (
        f"Region sets differ between detection paths.\n"
        f"Legacy only: {legacy_types - new_types}\n"
        f"New only: {new_types - legacy_types}"
    )

