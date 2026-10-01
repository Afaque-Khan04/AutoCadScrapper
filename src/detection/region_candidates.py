"""
Orchestrator: page-wide candidate detection -> confidence scoring ->
filtered list of regions ready for the existing table_builder assembly
step.
"""

from __future__ import annotations

from pathlib import Path

# pyrefly: ignore [missing-import]
from src.detection.dictionaries import DictionaryStore, load_default_stores
# pyrefly: ignore [missing-import]
from src.detection.scoring import RegionCandidate, ScoredRegion, ScoringWeights, score_all
# pyrefly: ignore [missing-import]
from src.detection.title_block_zone import BBox, TitleBlockZone, detect_title_block_zone

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "dictionaries"


def find_candidate_regions_for_page(
    page_width: float,
    page_height: float,
    raw_candidates: list[RegionCandidate],
    rect_candidates_for_zone: list[BBox],
    allow_store: DictionaryStore | None = None,
    deny_store: DictionaryStore | None = None,
    weights: ScoringWeights | None = None,
) -> list[ScoredRegion]:
    allow_store, deny_store = _resolve_stores(allow_store, deny_store)

    zone = detect_title_block_zone(
        page_width=page_width,
        page_height=page_height,
        rect_candidates=rect_candidates_for_zone,
    )

    return score_all(raw_candidates, allow_store, deny_store, zone, weights)


def _resolve_stores(
    allow_store: DictionaryStore | None,
    deny_store: DictionaryStore | None,
) -> tuple[DictionaryStore, DictionaryStore]:
    if allow_store is not None and deny_store is not None:
        return allow_store, deny_store
    loaded_allow, loaded_deny = load_default_stores(DEFAULT_DATA_DIR)
    return allow_store or loaded_allow, deny_store or loaded_deny
