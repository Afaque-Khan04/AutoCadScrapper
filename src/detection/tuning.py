"""
Weight tuning harness for the confidence-based ensemble scorer.
"""

from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import dataclass
from pathlib import Path

from src.detection.dictionaries import DictionaryStore, load_default_stores
from src.detection.scoring import RegionCandidate, ScoringWeights, score_region
from src.detection.title_block_zone import BBox, TitleBlockZone

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LABELED_DIR = DATA_DIR / "labeled_candidates"
DICT_DIR = DATA_DIR / "dictionaries"


@dataclass
class LabeledCandidate:
    source_pdf: str
    label: str
    expected_keep: bool
    candidate: RegionCandidate
    title_block_zone: TitleBlockZone


@dataclass
class Metrics:
    accuracy: float
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    tn: int
    fn: int

    def __str__(self) -> str:
        return (
            f"acc={self.accuracy:.3f} prec={self.precision:.3f} "
            f"rec={self.recall:.3f} f1={self.f1:.3f} "
            f"(tp={self.tp} fp={self.fp} tn={self.tn} fn={self.fn})"
        )


def _bbox_from_dict(d: dict) -> BBox:
    return BBox(x0=d["x0"], y0=d["y0"], x1=d["x1"], y1=d["y1"])


def load_labeled_candidates(labeled_dir: Path = LABELED_DIR) -> list[LabeledCandidate]:
    results: list[LabeledCandidate] = []
    for path in sorted(labeled_dir.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        zone = TitleBlockZone(bbox=_bbox_from_dict(raw["title_block_zone"]), detection_method="border_rect")
        for c in raw["candidates"]:
            candidate = RegionCandidate(
                bbox=_bbox_from_dict(c["bbox"]),
                structure_source=c["structure_source"],
                header_texts=c["header_texts"],
                row_count=c["row_count"],
                col_count=c["col_count"],
                nearby_title_text=c.get("nearby_title_text"),
                nearby_title_regex_hit=c.get("nearby_title_regex_hit", False),
            )
            results.append(
                LabeledCandidate(
                    source_pdf=raw["source_pdf"],
                    label=c["label"],
                    expected_keep=c["expected_keep"],
                    candidate=candidate,
                    title_block_zone=zone,
                )
            )
    return results


def evaluate(
    weights: ScoringWeights,
    labeled: list[LabeledCandidate],
    allow_store: DictionaryStore,
    deny_store: DictionaryStore,
) -> Metrics:
    tp = fp = tn = fn = 0
    for lc in labeled:
        result = score_region(lc.candidate, allow_store, deny_store, lc.title_block_zone, weights)
        predicted = result.keep
        if predicted and lc.expected_keep:
            tp += 1
        elif predicted and not lc.expected_keep:
            fp += 1
        elif not predicted and not lc.expected_keep:
            tn += 1
        else:
            fn += 1

    total = tp + fp + tn + fn
    accuracy = (tp + tn) / total if total else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return Metrics(accuracy=accuracy, precision=precision, recall=recall, f1=f1, tp=tp, fp=fp, tn=tn, fn=fn)


DEFAULT_GRID = {
    "structure_found": [20, 40, 60],
    "allow_list": [30, 45, 60],
    "deny_list": [-90, -70, -50],
    "inside_title_block": [-50, -30, -15],
    "nearby_title": [5, 15, 25],
    "shape_sanity": [5, 10, 15],
    "confidence_threshold": [30, 50, 70],
    "fuzzy_threshold": [75, 85, 95],
}


def grid_search(
    labeled: list[LabeledCandidate],
    allow_store: DictionaryStore,
    deny_store: DictionaryStore,
    grid: dict[str, list[float]] = DEFAULT_GRID,
    metric: str = "accuracy",
) -> list[tuple[ScoringWeights, Metrics]]:
    keys = list(grid.keys())
    value_lists = [grid[k] for k in keys]

    results: list[tuple[ScoringWeights, Metrics]] = []
    for combo in itertools.product(*value_lists):
        weights = ScoringWeights(**dict(zip(keys, combo)))
        m = evaluate(weights, labeled, allow_store, deny_store)
        results.append((weights, m))

    results.sort(key=lambda pair: getattr(pair[1], metric), reverse=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Grid-search scoring weights against labeled candidates.")
    parser.add_argument("--metric", default="accuracy", choices=["accuracy", "precision", "recall", "f1"])
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args()

    labeled = load_labeled_candidates()
    if not labeled:
        print(f"No labeled candidates found in {LABELED_DIR} -- nothing to tune against.")
        return

    pdf_names = sorted({lc.source_pdf for lc in labeled})
    print(f"Loaded {len(labeled)} labeled candidates from {len(pdf_names)} PDF(s): {', '.join(pdf_names)}")
    if len(pdf_names) < 3:
        print(
            "NOTE: fewer than 3 labeled PDFs -- ranking below is likely underdetermined "
            "(many weight combos will tie). Treat this as a smoke test, not a tuning result, "
            "until more PDFs are added to data/labeled_candidates/."
        )
    print()

    allow_store, deny_store = load_default_stores(DICT_DIR)
    results = grid_search(labeled, allow_store, deny_store, metric=args.metric)

    top_score = getattr(results[0][1], args.metric)
    tied = sum(1 for _, m in results if getattr(m, args.metric) == top_score)
    print(f"{tied} of {len(results)} combinations tie for the best {args.metric} ({top_score:.3f}).")
    print()

    print(f"Top {args.top} combinations by {args.metric}:")
    for i, (weights, m) in enumerate(results[: args.top], start=1):
        print(f"\n#{i}  {m}")
        print(
            f"    structure_found={weights.structure_found} allow_list={weights.allow_list} "
            f"deny_list={weights.deny_list} inside_title_block={weights.inside_title_block}"
        )
        print(
            f"    nearby_title={weights.nearby_title} shape_sanity={weights.shape_sanity} "
            f"confidence_threshold={weights.confidence_threshold} fuzzy_threshold={weights.fuzzy_threshold}"
        )


if __name__ == "__main__":
    main()
