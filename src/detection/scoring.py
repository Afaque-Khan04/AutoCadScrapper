"""
Confidence-based ensemble scorer for candidate regions.

Replaces "does the title regex match" with a weighted combination of
signals, per the approach agreed in project discussion:

  1. Structural signal (grid/text-cluster found a real table shape) -- strong
  2. Header allow-list match                                        -- strong positive
  3. Header deny-list match                                         -- strong negative
  4. Inside title-block zone                                        -- negative
  5. Nearby title-like text (regex), if present                     -- weak positive, supporting only
  6. Row/column shape sanity (row_count, col_count heuristics)       -- weak

Each signal contributes a bounded score; the sum is clamped and
compared against CONFIDENCE_THRESHOLD. Every candidate keeps its full
signal breakdown so a human reviewer (or a debug log during the
benchmark test) can see *why* a region was kept or rejected, not just
the final verdict -- this is worth surfacing as a `confidence` /
`signal_breakdown` field in canonical JSON later, not just an internal
detail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Any

from src.detection.dictionaries import DictionaryStore, MatchResult
from src.detection.title_block_zone import BBox, TitleBlockZone, is_inside_zone

StructureSource = Literal["vector_grid", "text_clustering", "none"]

WEIGHT_STRUCTURE_FOUND = 40
WEIGHT_ALLOW_LIST_MATCH = 45
WEIGHT_DENY_LIST_MATCH = -70
WEIGHT_INSIDE_TITLE_BLOCK = -30
WEIGHT_NEARBY_TITLE_TEXT = 15
WEIGHT_SHAPE_SANITY = 10

CONFIDENCE_THRESHOLD = 50


@dataclass
class ScoringWeights:
    structure_found: float = WEIGHT_STRUCTURE_FOUND
    allow_list: float = WEIGHT_ALLOW_LIST_MATCH
    deny_list: float = WEIGHT_DENY_LIST_MATCH
    inside_title_block: float = WEIGHT_INSIDE_TITLE_BLOCK
    nearby_title: float = WEIGHT_NEARBY_TITLE_TEXT
    shape_sanity: float = WEIGHT_SHAPE_SANITY
    confidence_threshold: float = CONFIDENCE_THRESHOLD
    fuzzy_threshold: float = 85.0


@dataclass
class RegionCandidate:
    bbox: BBox
    structure_source: StructureSource
    header_texts: list[str] = field(default_factory=list)
    row_count: int = 0
    col_count: int = 0
    nearby_title_text: str | None = None
    nearby_title_regex_hit: bool = False
    retained_grid: Any = None  # Holds pre-built TableGrid / structure object to avoid duplicate detection passes


@dataclass
class SignalBreakdown:
    structure_found: float = 0.0
    allow_list: float = 0.0
    deny_list: float = 0.0
    title_block_zone: float = 0.0
    nearby_title: float = 0.0
    shape_sanity: float = 0.0

    def total(self) -> float:
        return (
            self.structure_found
            + self.allow_list
            + self.deny_list
            + self.title_block_zone
            + self.nearby_title
            + self.shape_sanity
        )


@dataclass
class ScoredRegion:
    candidate: RegionCandidate
    breakdown: SignalBreakdown
    confidence: float
    keep: bool
    best_allow_match: MatchResult | None
    best_deny_match: MatchResult | None


def _shape_sanity_score(row_count: int, col_count: int, weight: float) -> float:
    if col_count == 0 or row_count == 0:
        return 0.0
    if col_count >= 5:
        return -weight
    return weight


def score_region(
    candidate: RegionCandidate,
    allow_store: DictionaryStore,
    deny_store: DictionaryStore,
    title_block_zone: TitleBlockZone,
    weights: ScoringWeights | None = None,
) -> ScoredRegion:
    w = weights or ScoringWeights()
    breakdown = SignalBreakdown()

    # 1. Structural signal
    if candidate.structure_source in ("vector_grid", "text_clustering"):
        breakdown.structure_found = w.structure_found

    # 2 & 3. Header dictionary matches
    allow_matches = (
        allow_store.match_any(candidate.header_texts, threshold=w.fuzzy_threshold)
        if candidate.header_texts
        else []
    )
    deny_matches = (
        deny_store.match_any(candidate.header_texts, threshold=w.fuzzy_threshold)
        if candidate.header_texts
        else []
    )

    best_allow = max(allow_matches, key=lambda m: m.score, default=None)
    best_deny = max(deny_matches, key=lambda m: m.score, default=None)

    if best_allow and best_allow.matched:
        breakdown.allow_list = w.allow_list
    if best_deny and best_deny.matched:
        breakdown.deny_list = w.deny_list

    # 4. Title block zone
    if is_inside_zone(candidate.bbox, title_block_zone):
        breakdown.title_block_zone = w.inside_title_block

    # 5. Nearby title text
    if candidate.nearby_title_regex_hit:
        breakdown.nearby_title = w.nearby_title

    # 6. Shape sanity
    breakdown.shape_sanity = _shape_sanity_score(candidate.row_count, candidate.col_count, w.shape_sanity)

    confidence = breakdown.total()
    keep = confidence >= w.confidence_threshold

    return ScoredRegion(
        candidate=candidate,
        breakdown=breakdown,
        confidence=confidence,
        keep=keep,
        best_allow_match=best_allow,
        best_deny_match=best_deny,
    )


def score_all(
    candidates: list[RegionCandidate],
    allow_store: DictionaryStore,
    deny_store: DictionaryStore,
    title_block_zone: TitleBlockZone,
    weights: ScoringWeights | None = None,
) -> list[ScoredRegion]:
    return [score_region(c, allow_store, deny_store, title_block_zone, weights) for c in candidates]
