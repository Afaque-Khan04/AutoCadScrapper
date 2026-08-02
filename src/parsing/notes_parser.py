"""
Parser for non-schedule engineering notes panels (General Notes, Legends, Specifications).
Converts spatial text blocks into structured JSON containing canonical key-value pairs,
nested subsections, legends, and metadata statements.

Handles:
  - Vector bounding box discovery (trims region at vector border/bottom line y=402.6,
    explicitly excluding CLIENT and title block metadata below it).
  - Word deduplication for overlaid CAD text tokens.
  - Multi-line key assembly (e.g. "LIFTING,TRANSPORTATION AND ERECTION - M35").
  - Nested section headers (e.g. "COVER: COLUMN - 40mm").
  - Standalone metadata statements (e.g. "ALL DIMENSIONS ARE IN MM").
"""

from __future__ import annotations
import re
from typing import Any
import fitz  # PyMuPDF

from ..tables.anchor_detection import ScheduleAnchor
from ..tables.text_geometry import cluster_words_into_rows, split_by_largest_gap


ROW_TOLERANCE = 6.0         # pts; max y-diff for words in same line
DEFAULT_SEARCH_DEPTH = 350.0 # pts; default depth if no bottom vector line exists
PADDING = 4.0               # pts; padding around discovered bounds

# Blockers — text keywords that indicate the end of General Notes / Legends panel
TITLE_BLOCK_EXCLUSIONS = [
    re.compile(r"^client:?$", re.IGNORECASE),
    re.compile(r"^project:?$", re.IGNORECASE),
    re.compile(r"^revision\s+schedule", re.IGNORECASE),
    re.compile(r"^structural\s+consultant", re.IGNORECASE),
    re.compile(r"^drawing\s+title", re.IGNORECASE),
]


def normalize_key(raw_key: str) -> str:
    """Converts raw string to snake_case canonical key."""
    s = raw_key.strip().lower()
    s = re.sub(r'[^a-z0-9\s]', '', s)
    s = re.sub(r'\s+', '_', s)
    return s


def _discover_notes_bounds(
    page: fitz.Page,
    anchor: ScheduleAnchor,
    page_rect: fitz.Rect,
) -> fitz.Rect:
    """
    Discovers actual vector bounding box for notes panel.
    Trims bottom boundary BEFORE any title block keyword (e.g. 'CLIENT:')
    or bottom bounding line (e.g. y=402.6 / 410.3).
    """
    drawings = page.get_drawings()
    h_lines = []
    v_lines = []

    for d in drawings:
        for item in d['items']:
            if item[0] == 'l':
                p1, p2 = item[1], item[2]
                dx, dy = abs(p2.x - p1.x), abs(p2.y - p1.y)
                if dy < 2 and dx > 30:  # horizontal line
                    h_lines.append((p1.y, min(p1.x, p2.x), max(p1.x, p2.x)))
                elif dx < 2 and dy > 30:  # vertical line
                    v_lines.append((p1.x, min(p1.y, p2.y), max(p1.y, p2.y)))

    # 1. Exclusion Y (e.g. CLIENT: block)
    blocks = page.get_text("blocks")
    exclusion_y = page_rect.y1
    for b in blocks:
        if b[6] == 0 and b[1] > anchor.bbox.y1 and b[0] >= anchor.bbox.x0 - 50:  # pyright: ignore[reportOperatorIssue] — fitz block-tuple elements are typed loosely
            text = " ".join(b[4].split()).lower()
            if any(excl.search(text) for excl in TITLE_BLOCK_EXCLUSIONS):
                if b[1] < exclusion_y:  # pyright: ignore[reportOperatorIssue]
                    exclusion_y = b[1]

    # 2. Horizontal lines around anchor
    # Top line IMMEDIATELY above anchor (max y <= anchor.bbox.y0 + 5)
    h_above = [y for y, x0, x1 in h_lines if y <= anchor.bbox.y0 + 5 and x0 - 30 <= anchor.bbox.x0 <= x1 + 30]
    top_y = max(h_above) if h_above else max(page_rect.y0, anchor.bbox.y0 - 10)

    h_below = [y for y, x0, x1 in h_lines if anchor.bbox.y1 < y < exclusion_y and (x0 - 30 <= anchor.bbox.x0 <= x1 + 30)]
    bottom_y = max(h_below) if h_below else min(exclusion_y - 5, anchor.bbox.y1 + DEFAULT_SEARCH_DEPTH)  # pyright: ignore[reportOperatorIssue]

    # 3. Vertical x-bounds
    v_matching = [x for x, y0, y1 in v_lines if y0 <= top_y + 15 and y1 >= bottom_y - 15]
    left_verts = [x for x in v_matching if x <= anchor.bbox.x0 + 15]
    right_verts = [x for x in v_matching if x >= anchor.bbox.x1 - 15]

    x_left = max(left_verts) if left_verts else max(page_rect.x0, anchor.bbox.x0 - 20)
    x_right = min(right_verts) if right_verts else min(page_rect.x1, anchor.bbox.x1 + 200)

    return fitz.Rect(
        x_left + 2,
        top_y + 2,
        x_right - 2,
        bottom_y - 2,
    )


def parse_notes_region(
    page: fitz.Page,
    anchor: ScheduleAnchor,
    page_rect: fitz.Rect,
) -> dict:
    """
    Parses a General Notes or Legend region into canonical JSON.
    Excludes CLIENT and surrounding boxes.
    """
    search_region = _discover_notes_bounds(page, anchor, page_rect)

    # Extract words
    words = page.get_text("words")
    region_words = []
    for w in words:
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2  # pyright: ignore[reportOperatorIssue] — fitz word-tuple elements are typed loosely
        if search_region.x0 <= cx <= search_region.x1 and search_region.y0 <= cy <= search_region.y1:
            region_words.append({
                'x0': w[0], 'y0': w[1], 'x1': w[2], 'y1': w[3],
                'text': w[4], 'cx': cx, 'cy': cy
            })

    # Deduplicate overlaid CAD word tokens
    deduped = []
    for w in region_words:
        if not any(e['text'] == w['text'] and abs(e['cx'] - w['cx']) < 2.0 and abs(e['cy'] - w['cy']) < 2.0 for e in deduped):
            deduped.append(w)

    # Cluster into lines — shared running-average row clustering
    # (same utility text_clustering.py uses, so both stay in sync).
    rows = cluster_words_into_rows(deduped, ROW_TOLERANCE)
    rows.sort(key=lambda r: r['cy'])
    lines = []
    for r in rows:
        r['words'].sort(key=lambda w: w['x0'])
        lines.append({
            'cy': r['cy'],
            'text': " ".join(w['text'] for w in r['words']),
            'words': r['words']
        })

    # Structured parsing
    result: dict[str, Any] = {
        "table_type": anchor.table_type,
        "region_type": anchor.region_type,
        "title_raw": anchor.matched_text,
        "source_region_bbox": [search_region.x0, search_region.y0, search_region.x1, search_region.y1],
        "general_notes": {},
        "legends": {},
        "metadata": [],
    }

    current_section = "general_notes"
    current_dict = result["general_notes"]

    i = 0
    while i < len(lines):
        text = lines[i]['text']

        # Header check (e.g. GENERAL NOTES:, COVER:, LEGENDS:)
        if text.endswith(":") and "-" not in text:
            header_name = text[:-1].strip().lower()
            if "general note" in header_name:
                current_section = "general_notes"
                current_dict = result["general_notes"]
            elif "legend" in header_name:
                current_section = "legends"
                current_dict = result["legends"]
            else:
                sec_key = normalize_key(header_name)
                if sec_key not in result["general_notes"]:
                    result["general_notes"][sec_key] = {}
                current_dict = result["general_notes"][sec_key]
            i += 1
            continue

        # Collect lines for single or multi-line key-value entry.
        # Standalone notes (no dash anywhere in the entry) are handled
        # generically below by the has_dash branch — no keyword lookup.
        entry_lines = [lines[i]]
        j = i + 1
        has_dash = "-" in text

        while j < len(lines):
            next_line = lines[j]
            next_text = next_line['text']
            # Break on a new section header, and on the standalone
            # dimensions note which sits structurally adjacent to the
            # previous entry (just past the 20pt continuation threshold
            # on the benchmark PDF) — guard against it being absorbed
            # into that entry's value.
            if (next_text.endswith(":") and "-" not in next_text) or ("ALL DIMENSIONS" in next_text.upper()):
                break
            if "-" in next_text:
                if has_dash:
                    break
                else:
                    entry_lines.append(next_line)
                    has_dash = True
                    j += 1
                    continue
            else:
                if has_dash:
                    if next_line['cy'] - entry_lines[-1]['cy'] < 20.0:
                        entry_lines.append(next_line)
                        j += 1
                        continue
                    else:
                        break
                else:
                    entry_lines.append(next_line)
                    j += 1
                    continue

        i = j

        # Process entry words
        all_words = [w for l in entry_lines for w in l['words']]
        dash_words = [w for w in all_words if w['text'] == '-']

        if dash_words:
            # Split key/value at the largest horizontal gap instead of
            # anchoring to one dash word's position — robust to imperfect
            # column alignment and to multi-line entries where the dash
            # sits on its own line (e.g. "LIFTING,TRANSPORTATION / - M35 /
            # AND ERECTION" on the benchmark PDF).
            key_words, val_words = split_by_largest_gap(all_words, axis="x")
            # The literal dash token may land on either side of the split
            # — drop it so it never pollutes key or value text.
            key_words = [w for w in key_words if w['text'] != '-']
            val_words = [w for w in val_words if w['text'] != '-']

            key_words.sort(key=lambda w: (round(w['cy'] / 5) * 5, w['x0']))
            val_words.sort(key=lambda w: (round(w['cy'] / 5) * 5, w['x0']))

            key_str = " ".join(w['text'] for w in key_words)
            val_str = " ".join(w['text'] for w in val_words)

            canon_key = normalize_key(key_str)
            if canon_key:
                current_dict[canon_key] = val_str
        else:
            # No dash anywhere in the entry → it's a standalone note with
            # no paired value (e.g. "ALL DIMENSIONS ARE IN MM"), not a
            # mis-keyed empty field. Send it to metadata instead.
            text_str = " ".join(w['text'] for w in all_words)
            if text_str.strip():
                result["metadata"].append(text_str)

    return result
