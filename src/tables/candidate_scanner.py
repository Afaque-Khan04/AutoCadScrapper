"""
Page-wide candidate region detection for confidence-based classification.

Scans an entire page (without title anchors) using grid_reconstructor.py
for vector grids and text_clustering.py for text-based tables/panels.
Populates RegionCandidate objects with extracted header_texts, shape
metadata, nearby_title_regex_hit tags, and carries forward pre-built
TableGrid objects to eliminate redundant extraction passes.
"""

from __future__ import annotations
import fitz

from ..detection.scoring import RegionCandidate
from ..detection.title_block_zone import BBox
from ..utils.constants import SCHEDULE_TITLE_PATTERNS, NOTES_TITLE_PATTERNS, SCHEDULE_TITLE_EXCLUSIONS
from .grid_reconstructor import (
    extract_grid_lines,
    build_grid,
    refine_region_bottom,
    extract_closed_rectangles,
    TableGrid,
)
from .text_clustering import build_text_grid
from .header_normalizer import normalize_header


MIN_CANDIDATE_WIDTH = 30.0     # pts
MIN_CANDIDATE_HEIGHT = 15.0    # pts
PROXIMITY_SEARCH_MARGIN = 40.0 # pts search range around candidate for title hits


def _extract_header_texts_from_grid(page: fitz.Page, grid: TableGrid) -> list[str]:
    """Helper to extract header texts from candidate grid."""
    headers: list[str] = []
    n_cols = len(grid.col_positions) - 1
    if n_cols <= 0 or len(grid.row_positions) < 2:
        return headers

    words = page.get_text("words")
    # For vector grids, check row 0. For text clustering panels (e.g. General Notes), check rows 0..N
    max_rows = len(grid.row_positions) - 1 if grid.source == "text_clustering" else 1

    for r in range(max_rows):
        h_top = grid.row_positions[r]
        h_bot = grid.row_positions[r + 1]
        for c in range(n_cols):
            cell_rect = fitz.Rect(grid.col_positions[c], h_top, grid.col_positions[c + 1], h_bot)
            matched_words = []
            for w in words:
                # pyrefly: ignore [unsupported-operation]
                cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
                if cell_rect.x0 <= cx <= cell_rect.x1 and cell_rect.y0 <= cy <= cell_rect.y1:
                    matched_words.append(w[4])
            raw_header = " ".join(matched_words).strip()
            if raw_header and raw_header not in headers:
                headers.append(raw_header)

    return headers



def _check_nearby_title_regex(page: fitz.Page, candidate_bbox: fitz.Rect) -> tuple[bool, str | None]:
    """
    Checks if a title-like text string sits near candidate_bbox using the
    proximity search patterns from anchor_detection.py.
    """
    search_rect = fitz.Rect(
        candidate_bbox.x0 - PROXIMITY_SEARCH_MARGIN,
        candidate_bbox.y0 - PROXIMITY_SEARCH_MARGIN,
        candidate_bbox.x1 + PROXIMITY_SEARCH_MARGIN,
        candidate_bbox.y1 + PROXIMITY_SEARCH_MARGIN,
    )

    blocks = page.get_text("blocks")
    for block in blocks:
        if block[6] != 0:  # skip images
            continue
        bx0, by0, bx1, by1, text = block[0], block[1], block[2], block[3], block[4]
        b_rect = fitz.Rect(bx0, by0, bx1, by1)
        if search_rect.intersects(b_rect):
            normalized = " ".join(text.split()).lower()
            if any(excl.search(normalized) for excl in SCHEDULE_TITLE_EXCLUSIONS):
                continue

            for table_type, patterns in SCHEDULE_TITLE_PATTERNS.items():
                for pattern in patterns:
                    if pattern.search(normalized):
                        return True, text.strip()

            for region_type, patterns in NOTES_TITLE_PATTERNS.items():
                for pattern in patterns:
                    if pattern.search(normalized):
                        return True, text.strip()

    return False, None


def _find_vector_grid_candidates(page: fitz.Page) -> list[RegionCandidate]:
    """
    Discovers candidate table regions across the full page using vector grid lines.
    Reuses grid_reconstructor's bracket-x and line clustering logic.
    """
    candidates: list[RegionCandidate] = []
    page_rect = page.rect
    all_lines = extract_grid_lines(page, page_rect)

    horiz_lines = sorted([l for l in all_lines if l.orientation == "horizontal"], key=lambda l: l.position)
    if not horiz_lines:
        return candidates

    clusters: list[list] = []
    current_cluster: list = [horiz_lines[0]]
    for h in horiz_lines[1:]:
        if h.position - current_cluster[-1].position <= 40.0:
            current_cluster.append(h)
        else:
            if len(current_cluster) >= 2:
                clusters.append(current_cluster)
            current_cluster = [h]
    if len(current_cluster) >= 2:
        clusters.append(current_cluster)

    vert_lines = [l for l in all_lines if l.orientation == "vertical"]

    for cluster in clusters:
        c_top = cluster[0].position
        c_bottom = cluster[-1].position

        overlapping_verts = [
            v for v in vert_lines
            if v.start <= c_bottom + 5.0 and v.end >= c_top - 5.0
        ]

        if not overlapping_verts:
            continue

        sorted_verts = sorted(overlapping_verts, key=lambda v: v.position)
        vert_groups: list[list] = [[sorted_verts[0]]]
        for v in sorted_verts[1:]:
            prev_x = vert_groups[-1][-1].position
            if v.position - prev_x > 20.0:
                vert_groups.append([v])
            else:
                vert_groups[-1].append(v)

        for v_group in vert_groups:
            if len(v_group) < 2:
                continue
            x_left = min(v.position for v in v_group)
            x_right = max(v.position for v in v_group)

            w = x_right - x_left
            h = c_bottom - c_top
            if w < MIN_CANDIDATE_WIDTH or h < MIN_CANDIDATE_HEIGHT:
                continue

            search_region = fitz.Rect(x_left - 2.0, c_top - 2.0, x_right + 2.0, c_bottom + 2.0)
            raw_lines = extract_grid_lines(page, search_region)
            region, lines = refine_region_bottom(search_region, raw_lines)
            grid = build_grid(lines)

            if grid is not None and len(grid.row_positions) >= 2 and len(grid.col_positions) >= 2:
                headers = _extract_header_texts_from_grid(page, grid)
                regex_hit, title_text = _check_nearby_title_regex(page, region)

                candidates.append(
                    RegionCandidate(
                        bbox=BBox(x0=region.x0, y0=region.y0, x1=region.x1, y1=region.y1),
                        structure_source="vector_grid",
                        header_texts=headers,
                        row_count=len(grid.row_positions) - 1,
                        col_count=len(grid.col_positions) - 1,
                        nearby_title_text=title_text,
                        nearby_title_regex_hit=regex_hit,
                        retained_grid=grid,
                    )
                )

    return candidates


def _cluster_text_blocks(blocks: list[fitz.Rect], max_dx: float = 15.0, max_dy: float = 8.0) -> list[fitz.Rect]:
    """Groups nearby/adjacent text block bounding boxes into coherent text regions."""
    if not blocks:
        return []
    clusters: list[fitz.Rect] = [fitz.Rect(b) for b in blocks]
    changed = True
    while changed:
        changed = False
        new_clusters: list[fitz.Rect] = []
        visited = [False] * len(clusters)
        for i in range(len(clusters)):
            if visited[i]:
                continue
            curr = fitz.Rect(clusters[i])
            visited[i] = True
            for j in range(i + 1, len(clusters)):
                if visited[j]:
                    continue
                o = clusters[j]
                if (curr.x0 - max_dx <= o.x1 and o.x0 <= curr.x1 + max_dx and
                    curr.y0 - max_dy <= o.y1 and o.y0 <= curr.y1 + max_dy):
                    curr = fitz.Rect(
                        min(curr.x0, o.x0),
                        min(curr.y0, o.y0),
                        max(curr.x1, o.x1),
                        max(curr.y1, o.y1),
                    )
                    visited[j] = True
                    changed = True
            new_clusters.append(curr)
        clusters = new_clusters
    return clusters


def _find_text_clustering_candidates(
    page: fitz.Page,
    existing_vector_candidates: list[RegionCandidate],
) -> list[RegionCandidate]:
    """
    Discovers candidate text regions (like General Notes or text-only tables) across the page.
    Filters out text covered by already-found vector grids.
    MIN_TOTAL_ROWS = 2 ensures Weight Schedule / 2-row tables survive.
    """
    candidates: list[RegionCandidate] = []
    vector_bboxes = [
        fitz.Rect(c.bbox.x0, c.bbox.y0, c.bbox.x1, c.bbox.y1)
        for c in existing_vector_candidates
    ]

    blocks = page.get_text("blocks")
    raw_block_rects = [
        fitz.Rect(b[0], b[1], b[2], b[3])
        for b in blocks
        if b[6] == 0 and not any(fitz.Rect(c.bbox.x0, c.bbox.y0, c.bbox.x1, c.bbox.y1).intersects(fitz.Rect(b[0], b[1], b[2], b[3])) for c in existing_vector_candidates)
    ]

    clustered_regions = _cluster_text_blocks(raw_block_rects, max_dx=15.0, max_dy=8.0)

    for b_rect in clustered_regions:
        if b_rect.width < MIN_CANDIDATE_WIDTH or b_rect.height < MIN_CANDIDATE_HEIGHT:
            continue

        grid = build_text_grid(page, b_rect)
        if grid is not None and len(grid.row_positions) >= 3:
            row_count = len(grid.row_positions) - 1
            col_count = len(grid.col_positions) - 1
            headers = _extract_header_texts_from_grid(page, grid)
            regex_hit, title_text = _check_nearby_title_regex(page, b_rect)

            candidates.append(
                RegionCandidate(
                    bbox=BBox(x0=b_rect.x0, y0=b_rect.y0, x1=b_rect.x1, y1=b_rect.y1),
                    structure_source="text_clustering",
                    header_texts=headers,
                    row_count=row_count,
                    col_count=col_count,
                    nearby_title_text=title_text,
                    nearby_title_regex_hit=regex_hit,
                    retained_grid=grid,
                )
            )

    return candidates




def scan_page_for_candidates(page: fitz.Page) -> tuple[list[RegionCandidate], list[BBox]]:
    """
    Main candidate scanner entry point.
    Returns:
       (raw_candidates, rect_candidates_for_zone)
    """
    rect_candidates_for_zone = extract_closed_rectangles(page)
    vector_candidates = _find_vector_grid_candidates(page)
    text_candidates = _find_text_clustering_candidates(page, vector_candidates)

    raw_candidates = vector_candidates + text_candidates
    return raw_candidates, rect_candidates_for_zone
