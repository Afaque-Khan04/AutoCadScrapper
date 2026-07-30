"""
Parses reinforcement/rebar shorthand notation found in schedule table
cells (Beam/Slab/Column schedules) into structured fields.

Handles the notational variants confirmed against a real benchmark
sheet (Schedule of Beams), since there is no single universal
convention across drafting offices:
  - "4-T20"           -> count=4, bar_type="T20"
  - "2-16\u00d8"            -> count=2, diameter_mm=16
  - "2-16\u00d8+1-12\u00d8"     -> COMPOUND: two distinct bar groups in one cell
                          (seen in B6's bottom reinforcement: "2-16\u00d8+1-12\u00d8")
  - "T10@150c/c"      -> bar_type="T10", spacing_mm=150
  - "6\u00d8130C/C"        -> diameter_mm=6, spacing_mm=130 (no separator between dia and spacing;
                          this is the stirrup-notation style used throughout Image 1)

Because a cell can legitimately contain more than one bar group (main
bars + extra bars, or two different diameters), normalized_value for
a rebar cell is ALWAYS a list of group dicts -- never a single flat
dict -- even when there's only one group. This keeps downstream
consumers from having to special-case "is this one group or many".
"""

from __future__ import annotations
import re


# Order matters: more specific/constrained patterns first, so a
# compound-looking token isn't partially matched by a looser one.
_DIA_SPACING_SYMBOL = re.compile(
    r"(?P<diameter>\d+)\s*[\u00d8\u00f8]\s*(?P<spacing>\d+)\s*C\s*/\s*C", re.IGNORECASE
)  # "6\u00d8130C/C"

_LETTER_AT_SPACING = re.compile(
    r"(?P<bar_type>[A-Za-z]+\d+)\s*@\s*(?P<spacing>\d+)\s*C\s*/\s*C", re.IGNORECASE
)  # "T10@150c/c"

_COUNT_DIA_SYMBOL = re.compile(
    r"(?P<count>\d+)\s*-\s*(?P<diameter>\d+)\s*[\u00d8\u00f8]"
)  # "2-16\u00d8"

_COUNT_DIA_LETTER = re.compile(
    r"(?P<count>\d+)\s*-\s*(?P<bar_type>[A-Za-z]+\d+)"
)  # "4-T20"


def _parse_single_group(token: str) -> dict | None:
    token = token.strip()
    if not token:
        return None

    if m := _DIA_SPACING_SYMBOL.search(token):
        return {"diameter_mm": int(m.group("diameter")), "spacing_mm": int(m.group("spacing"))}

    if m := _LETTER_AT_SPACING.search(token):
        return {"bar_type": m.group("bar_type").upper(), "spacing_mm": int(m.group("spacing"))}

    if m := _COUNT_DIA_SYMBOL.search(token):
        return {"count": int(m.group("count")), "diameter_mm": int(m.group("diameter"))}

    if m := _COUNT_DIA_LETTER.search(token):
        return {"count": int(m.group("count")), "bar_type": m.group("bar_type").upper()}

    return None


def parse_rebar_value(raw_text: str) -> list[dict] | None:
    """
    Splits on '+' to handle compound cells (e.g. "2-16\u00d8+1-12\u00d8") and
    parses each group independently. Returns None if nothing
    recognizable was found in any group, so the caller can fall back
    to keeping raw_text with normalized_value=None rather than
    silently dropping data.
    """
    if not raw_text or not raw_text.strip():
        return None

    groups = [g for token in raw_text.split("+") if (g := _parse_single_group(token))]
    return groups or None
