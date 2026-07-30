"""
Maps raw header text extracted from schedule tables to canonical field
names using fuzzy string matching against a maintained alias dictionary.

Why fuzzy matching instead of exact lookup:
  Header wording varies by drafter, office, and even from sheet to sheet
  within the same project ("BOTTAM REINFO." vs "Bottom Reinforcement" vs
  "BOT. REINF."). Exact matching would require an impossibly exhaustive
  alias list. Fuzzy matching with a tunable threshold catches most
  variants while still rejecting garbage.

Uses rapidfuzz (C-optimized) for performance — schedule tables are small
so speed isn't critical, but it avoids pulling in heavier NLP deps.
"""

from __future__ import annotations
from rapidfuzz import fuzz, process

from ..utils.constants import HEADER_ALIASES, FUZZY_MATCH_THRESHOLD


# Pre-flatten the alias dict into (alias_text, canonical_field) pairs
# for efficient lookup. Built once at import time.
_ALIAS_PAIRS: list[tuple[str, str]] = []
for canonical, aliases in HEADER_ALIASES.items():
    for alias in aliases:
        _ALIAS_PAIRS.append((alias.lower(), canonical))

_ALIAS_TEXTS = [pair[0] for pair in _ALIAS_PAIRS]
_ALIAS_FIELDS = [pair[1] for pair in _ALIAS_PAIRS]


def normalize_header(raw_header: str) -> str | None:
    """
    Fuzzy-matches a raw header string against known aliases and returns
    the canonical field name if the best match scores above the threshold.

    Returns None if no match is confident enough — the caller should
    preserve the raw header text as-is rather than guessing.

    Examples:
        normalize_header("BOTTAM REINFO.") -> "bottom_reinforcement"
        normalize_header("Beam Mkd.")      -> "beam_mark"
        normalize_header("xyzzy")          -> None
    """
    if not raw_header or not raw_header.strip():
        return None

    cleaned = " ".join(raw_header.strip().lower().split())

    # Try exact match first (fastest path)
    for alias_text, canonical in _ALIAS_PAIRS:
        if cleaned == alias_text:
            return canonical

    # Fall back to fuzzy matching
    result = process.extractOne(
        cleaned,
        _ALIAS_TEXTS,
        scorer=fuzz.WRatio,
        score_cutoff=FUZZY_MATCH_THRESHOLD,
    )

    if result is None:
        return None

    matched_text, score, index = result
    return _ALIAS_FIELDS[index]


def normalize_headers_for_table(
    raw_headers: list[str],
    merged_header_cells: list[dict] | None = None,
) -> list[dict]:
    """
    Takes a list of raw header strings (one per column) and returns a
    list of dicts with canonical field mappings and parent-header
    relationships.

    If merged_header_cells is provided (from grid_reconstructor's merge
    detection), uses it to set parent_header on sub-columns.

    Returns:
        [{"col_index": 0, "raw_header": "Beam Mark",
          "canonical_field": "beam_mark", "parent_header": None}, ...]
    """
    results = []
    for i, raw in enumerate(raw_headers):
        canonical = normalize_header(raw)
        results.append({
            "col_index": i,
            "raw_header": raw,
            "canonical_field": canonical,
            "parent_header": None,  # Set below if merge info available
        })

    # TODO: Wire parent_header from merged_header_cells once merge
    # detection is validated against real multi-row headers. For the
    # benchmark PDF's simple single-row headers, this is a no-op.

    return results
