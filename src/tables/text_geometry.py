"""
Shared text-geometry utilities for the extraction pipeline.

Both ``text_clustering.py`` (schedule tables without ruling lines) and
``notes_parser.py`` (General Notes / Legends panels) previously
maintained their own, slightly divergent implementations of "group
words into rows by y-proximity". This module centralises those
primitives so a fix to one is a fix to both, and provides the
gap-based split used for key/value separation in notes parsing.

Word dicts are expected to carry at least: ``text``, ``x0``, ``y0``,
``x1``, ``y1``, ``cx``, ``cy`` (the same shape produced by
``page.get_text("words")`` wrappers elsewhere in the codebase).
"""

from __future__ import annotations


def cluster_words_into_rows(words: list[dict], tolerance: float) -> list[dict]:
    """
    Groups word dicts into rows by y-center proximity, using a proper
    running average (not naive pairwise comparison) to avoid cy drift.

    Words are sorted by ``cy`` and clustered sequentially: a word joins
    the current cluster while its ``cy`` is within ``tolerance`` of the
    cluster's running-average center.

    Returns a list of row dicts ``{"cy": float, "words": list[dict]}``
    sorted top-to-bottom.
    """
    if not words:
        return []

    sorted_words = sorted(words, key=lambda w: w["cy"])
    rows: list[dict] = []
    current: list[dict] = [sorted_words[0]]
    current_cy = sorted_words[0]["cy"]

    for w in sorted_words[1:]:
        if abs(w["cy"] - current_cy) <= tolerance:
            current.append(w)
            # Running average: avoids drift from repeated pairwise averaging
            current_cy = (current_cy * (len(current) - 1) + w["cy"]) / len(current)
        else:
            rows.append({"cy": current_cy, "words": current})
            current = [w]
            current_cy = w["cy"]

    rows.append({"cy": current_cy, "words": current})
    return rows


def split_by_largest_gap(
    words: list[dict],
    axis: str = "x",
) -> tuple[list[dict], list[dict]]:
    """
    Splits a word list into two groups at the single largest gap along
    the given axis.

    For ``axis="x"`` the gap between consecutive words (sorted by cx)
    is ``next.x0 - prev.x1``; for ``axis="y"`` it is
    ``next.y0 - prev.y1``. The two groups keep the words' original
    objects, each preserving its own ordering from the sort.

    With fewer than two words, returns ``(words, [])``.

    Used for both n-way cell clustering (text_clustering.py) and 2-way
    key/value splitting (notes_parser.py).
    """
    if len(words) < 2:
        return list(words), []

    key = "cx" if axis == "x" else "cy"
    ordered = sorted(words, key=lambda w: w[key])

    best_index = 0
    best_gap = -1.0
    for i in range(len(ordered) - 1):
        if axis == "x":
            gap = ordered[i + 1]["x0"] - ordered[i]["x1"]
        else:
            gap = ordered[i + 1]["y0"] - ordered[i]["y1"]
        if gap > best_gap:
            best_gap = gap
            best_index = i

    return ordered[: best_index + 1], ordered[best_index + 1:]
