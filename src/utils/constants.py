"""
Centralized constants for the schedule extraction pipeline.

Schedule-title keyword patterns and header alias dictionaries live here
so they can be maintained in one place and shared across anchor detection,
header normalization, and validation modules.
"""

from __future__ import annotations
import re


# ---------------------------------------------------------------------------
# Schedule title patterns — used by anchor_detection.py
# ---------------------------------------------------------------------------
# Each key is a canonical table_type identifier.
# Values are lists of regex patterns (case-insensitive) that match known
# title-text variants for that schedule type.
#
# Extend this dict as new benchmark drawings surface — it is meant to
# grow, not be exhaustive on day one.

SCHEDULE_TITLE_PATTERNS: dict[str, list[re.Pattern]] = {
    # --- Structural schedules (beam/slab/column) ---
    "beam_schedule": [
        re.compile(r"schedule\s+of\s+beams?", re.IGNORECASE),
        re.compile(r"beam\s+schedule", re.IGNORECASE),
        re.compile(r"schedule\s+of\s+slab\s*beam", re.IGNORECASE),
    ],
    "slab_schedule": [
        re.compile(r"schedule\s+of\s+slabs?", re.IGNORECASE),
        re.compile(r"slab\s+schedule", re.IGNORECASE),
    ],
    "column_schedule": [
        re.compile(r"schedule\s+of\s+columns?", re.IGNORECASE),
        re.compile(r"column\s+schedule", re.IGNORECASE),
    ],
    "reinforcement_schedule": [
        re.compile(r"reinforcement\s+schedule", re.IGNORECASE),
        re.compile(r"schedule\s+of\s+reinforcement", re.IGNORECASE),
    ],
    "bar_bending_schedule": [
        re.compile(r"bar\s+bending\s+schedule", re.IGNORECASE),
        re.compile(r"\bbbs\b", re.IGNORECASE),
    ],
    "material_schedule": [
        re.compile(r"material\s+schedule", re.IGNORECASE),
        re.compile(r"schedule\s+of\s+materials?", re.IGNORECASE),
    ],
    "bill_of_materials": [
        re.compile(r"bill\s+of\s+material", re.IGNORECASE),
        re.compile(r"\bbom\b", re.IGNORECASE),
    ],

    # --- Precast / mould drawing schedules (from benchmark PDF) ---
    "weight_schedule": [
        re.compile(r"weight\s+schedule", re.IGNORECASE),
    ],
    "insert_schedule": [
        re.compile(r"insert\s+schedule", re.IGNORECASE),
    ],
    "dowel_bar_schedule": [
        re.compile(r"dowel\s+bar\s+schedule", re.IGNORECASE),
    ],
}

# Patterns to EXCLUDE — these look like schedules but aren't structural
# data tables (e.g. the revision history block in a title block).
SCHEDULE_TITLE_EXCLUSIONS: list[re.Pattern] = [
    re.compile(r"revision\s+schedule", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Header alias dictionary — used by header_normalizer.py
# ---------------------------------------------------------------------------
# Maps canonical field names to known raw-header text variants.
# The normalizer fuzzy-matches extracted header text against these aliases
# to produce consistent field names across different drafting conventions.
#
# Structure: canonical_field -> list of known aliases (lowercase).

HEADER_ALIASES: dict[str, list[str]] = {
    # --- Beam schedule fields ---
    "beam_mark":            ["beam mkd", "beam mkd.", "beam mark", "beam no", "mark"],
    "beam_size":            ["beam size", "size", "b x d", "bxd", "width x depth"],
    "top_reinforcement":    ["top reinfo", "top reinfo.", "top reinforcement", "top steel", "top bars"],
    "bottom_reinforcement": ["bottam reinfo", "bottam reinfo.", "bottom reinfo", "bottom reinfo.",
                             "bottom reinforcement", "bot reinforcement", "bot reinfo", "bot steel",
                             "bottom bars"],
    "straight_bars":        ["str", "str.", "straight", "straight bars"],
    "bent_bars":            ["bent", "bent bars", "bent up bars", "cranked"],
    "stirrups":             ["stirrups", "stirrup", "shear links", "links", "shear reinforcement"],
    "spacing":              ["spacing", "c/c", "c/c spacing"],
    "span":                 ["span", "clear span", "effective span"],
    "remarks":              ["remarks", "remark", "note", "notes"],

    # --- Slab schedule fields ---
    "slab_mark":            ["slab mkd", "slab mkd.", "slab mark", "slab no", "panel"],
    "slab_thickness":       ["thickness", "slab thickness", "depth"],
    "main_reinforcement":   ["main reinfo", "main reinfo.", "main reinforcement", "main bars",
                             "main steel"],
    "distribution_bars":    ["dist", "dist.", "distribution", "distribution bars", "dist steel"],

    # --- Column schedule fields ---
    "column_mark":          ["column mkd", "column mkd.", "column mark", "col mark", "col no"],
    "column_size":          ["column size", "col size", "section"],

    # --- Precast / mould schedule fields (benchmark PDF) ---
    "ref_no":               ["ref no", "ref no.", "reference", "reference no", "ref"],
    "type":                 ["type"],
    "count":                ["count", "qty", "quantity", "nos", "no."],
    "bar_diameter":         ["bar diameter", "dia", "diameter", "bar dia", "bar size"],
    "volume":               ["volume", "vol"],
    "weight":               ["weight", "wt", "wt."],
    "length":               ["length", "len", "bar length"],
}

# Minimum similarity score (0-100) for a fuzzy match to be accepted.
# Below this threshold, the raw header text is kept as-is with no
# canonical mapping — better to preserve the original than silently
# assign a wrong field name.
FUZZY_MATCH_THRESHOLD: int = 70
