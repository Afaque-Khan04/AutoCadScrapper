"""
Geometric pre-filter: is a candidate region inside the sheet's title
block / margin strip?

This is deliberately the cheapest, most drawing-convention-independent
signal in the ensemble -- it doesn't need to know anything about what a
title block *contains* (client name, revision table, consultant info),
only that title blocks conventionally sit inside their own bordered
frame in a fixed margin of the sheet (commonly the right edge and/or
bottom strip, per most CAD title block templates).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    def area(self) -> float:
        return max(0.0, self.x1 - self.x0) * max(0.0, self.y1 - self.y0)

    def contains(self, other: "BBox", tolerance: float = 2.0) -> bool:
        return (
            other.x0 >= self.x0 - tolerance
            and other.y0 >= self.y0 - tolerance
            and other.x1 <= self.x1 + tolerance
            and other.y1 <= self.y1 + tolerance
        )


@dataclass
class TitleBlockZone:
    bbox: BBox | None  # None if no title block frame was confidently detected
    detection_method: str  # "border_rect" | "not_found"


def detect_title_block_zone(
    page_width: float,
    page_height: float,
    rect_candidates: list[BBox],
    margin_fraction: float = 0.28,
) -> TitleBlockZone:
    margin_x0 = page_width * (1 - margin_fraction)

    def mostly_in_margin(b: BBox) -> bool:
        overlap_width = max(0.0, min(b.x1, page_width) - max(b.x0, margin_x0))
        box_width = max(1.0, b.x1 - b.x0)
        return (overlap_width / box_width) > 0.6

    candidates_in_margin = [b for b in rect_candidates if mostly_in_margin(b)]
    if not candidates_in_margin:
        return TitleBlockZone(bbox=None, detection_method="not_found")

    largest = max(candidates_in_margin, key=lambda b: b.area())
    return TitleBlockZone(bbox=largest, detection_method="border_rect")


def is_inside_zone(region_bbox: BBox, zone: TitleBlockZone) -> bool:
    if zone.bbox is None:
        return False
    return zone.bbox.contains(region_bbox)
