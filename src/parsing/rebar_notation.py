"""
Parses reinforcement/rebar shorthand notation found in schedule table
cells (Beam/Slab/Column/Insert/Dowel schedules) into structured fields.

Handles the notational variants confirmed against real benchmark sheets:
  - "4-T20"           -> count=4, bar_type="T20"
  - "2-16Ø"           -> count=2, diameter_mm=16
  - "2-16 Dia"        -> count=2, diameter_mm=16
  - "75 Dia"          -> diameter_mm=75
  - "25 mm"           -> diameter_mm=25
  - "12.9Ø"           -> diameter_mm=12.9
  - "2-16Ø+1-12Ø"     -> COMPOUND: two distinct bar groups in one cell
  - "T10@150c/c"      -> bar_type="T10", spacing_mm=150
  - "6Ø130C/C"        -> diameter_mm=6, spacing_mm=130

Because a cell can legitimately contain more than one bar group (main
bars + extra bars, or two different diameters), normalized_value for
a rebar cell is ALWAYS a list of group dicts -- never a single flat
dict -- even when there's only one group.
"""

from __future__ import annotations
import re


def _parse_num(val: str) -> int | float:
    v = float(val)
    return int(v) if v.is_integer() else v


# Order matters: more specific/constrained patterns first.
_DIA_SPACING_SYMBOL = re.compile(
    r"(?P<diameter>\d+(?:\.\d+)?)\s*(?:[\u00d8\u00f8]|\bdia\b)\s*(?P<spacing>\d+)\s*C\s*/\s*C", re.IGNORECASE
)  # "6Ø130C/C", "6 Dia 130 C/C"

_LETTER_AT_SPACING = re.compile(
    r"(?P<bar_type>[A-Za-z]+\d+)\s*@\s*(?P<spacing>\d+)\s*C\s*/\s*C", re.IGNORECASE
)  # "T10@150c/c"

_COUNT_DIA_SYMBOL = re.compile(
    r"(?:(?P<count>\d+)\s*-\s*)?(?P<diameter>\d+(?:\.\d+)?)\s*(?:[\u00d8\u00f8]|\bdia\b)", re.IGNORECASE
)  # "2-16Ø", "2-16 Dia", "75 Dia"

_COUNT_DIA_LETTER = re.compile(
    r"(?P<count>\d+)\s*-\s*(?P<bar_type>[A-Za-z]+\d+)", re.IGNORECASE
)  # "4-T20"

_STANDALONE_MM = re.compile(
    r"(?:(?P<count>\d+)\s*-\s*)?(?P<diameter>\d+(?:\.\d+)?)\s*mm\b", re.IGNORECASE
)  # "25 mm"


def _parse_single_group(token: str) -> dict | None:
    token = token.strip()
    if not token:
        return None

    if m := _DIA_SPACING_SYMBOL.search(token):
        return {"diameter_mm": _parse_num(m.group("diameter")), "spacing_mm": int(m.group("spacing"))}

    if m := _LETTER_AT_SPACING.search(token):
        return {"bar_type": m.group("bar_type").upper(), "spacing_mm": int(m.group("spacing"))}

    if m := _COUNT_DIA_SYMBOL.search(token):
        res = {"diameter_mm": _parse_num(m.group("diameter"))}
        if m.group("count"):
            res["count"] = int(m.group("count"))
        return res

    if m := _COUNT_DIA_LETTER.search(token):
        return {"count": int(m.group("count")), "bar_type": m.group("bar_type").upper()}

    if m := _STANDALONE_MM.search(token):
        res = {"diameter_mm": _parse_num(m.group("diameter"))}
        if m.group("count"):
            res["count"] = int(m.group("count"))
        return res

    return None


def parse_rebar_value(raw_text: str) -> list[dict] | None:
    """
    Splits on '+' to handle compound cells (e.g. "2-16Ø+1-12Ø") and
    parses each group independently. Returns None if nothing
    recognizable was found in any group, so the caller can fall back
    to keeping raw_text with normalized_value=None rather than
    silently dropping data.
    """
    if not raw_text or not raw_text.strip():
        return None

    groups = [g for token in raw_text.split("+") if (g := _parse_single_group(token))]
    return groups or None

