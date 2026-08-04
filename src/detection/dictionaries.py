"""
Allow-list / deny-list header dictionaries used by the confidence-based
region classifier.

Design intent (see docs/implementation_plan.md):
- The allow-list holds header/field vocabulary that indicates a genuine
  engineering schedule or notes panel (e.g. "Ref No", "Bar Diameter").
- The deny-list holds vocabulary that indicates a non-schedule table we
  want to exclude (title block / revision block admin fields, e.g.
  "Rev", "Chkd", "Appd").
- Every entry tracks which source PDF it was first seen in, so the
  dictionary's provenance is auditable as it grows across many PDFs.
- Matching is fuzzy (rapidfuzz), since real-world header text varies in
  casing, punctuation, and abbreviation ("Ref No." vs "REF NO" vs
  "Reference Number").

This module has no dependency on the PDF-parsing side of the pipeline.
It only knows about strings in, match scores out — wire it into the
region candidate flow in region_candidates.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path
from typing import Literal

from rapidfuzz import fuzz, process

Category = str  # e.g. "schedule_headers", "notes_structural_cues", "title_block_admin"
ListKind = Literal["allow", "deny"]

DEFAULT_FUZZY_THRESHOLD = 85  # 0-100, rapidfuzz token_sort_ratio scale


@dataclass
class DictionaryEntry:
    term: str
    category: Category
    source_pdf: str
    added_on: str = field(default_factory=lambda: date.today().isoformat())
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "DictionaryEntry":
        return DictionaryEntry(**d)


@dataclass
class MatchResult:
    matched: bool
    term: str | None
    category: Category | None
    score: float  # 0-100
    kind: ListKind


class DictionaryStore:
    """
    Holds one side (allow or deny) of the header dictionary.
    Persisted as a flat JSON list of DictionaryEntry dicts so it's easy
    to diff in version control as PDFs get added.
    """

    def __init__(self, kind: ListKind, entries: list[DictionaryEntry] | None = None):
        self.kind = kind
        self.entries: list[DictionaryEntry] = entries or []

    @classmethod
    def load(cls, path: Path, kind: ListKind) -> "DictionaryStore":
        if not path.exists():
            return cls(kind=kind, entries=[])
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(kind=kind, entries=[DictionaryEntry.from_dict(e) for e in raw])

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([e.to_dict() for e in self.entries], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def add_term(self, term: str, category: Category, source_pdf: str, notes: str = "") -> bool:
        """
        Adds a new term if it isn't already present (fuzzy-deduped against
        existing entries in the same category). Returns True if added.
        """
        existing_terms = [e.term for e in self.entries if e.category == category]
        if existing_terms:
            best = process.extractOne(term, existing_terms, scorer=fuzz.token_sort_ratio)
            if best and best[1] >= DEFAULT_FUZZY_THRESHOLD:
                return False  # already covered, skip duplicate
        self.entries.append(DictionaryEntry(term=term, category=category, source_pdf=source_pdf, notes=notes))
        return True

    def match(self, candidate_text: str, threshold: float = DEFAULT_FUZZY_THRESHOLD) -> MatchResult:
        """
        Fuzzy-matches a single header/field string against all entries.
        Returns the best match, or a non-match result if nothing clears
        the threshold.
        """
        if not self.entries:
            return MatchResult(matched=False, term=None, category=None, score=0.0, kind=self.kind)

        terms = [e.term for e in self.entries]
        best = process.extractOne(candidate_text, terms, scorer=fuzz.token_sort_ratio)
        if best is None or best[1] < threshold:
            return MatchResult(matched=False, term=None, category=None, score=best[1] if best else 0.0, kind=self.kind)

        matched_entry = self.entries[best[2]]
        return MatchResult(
            matched=True,
            term=matched_entry.term,
            category=matched_entry.category,
            score=best[1],
            kind=self.kind,
        )

    def match_any(self, header_texts: list[str], threshold: float = DEFAULT_FUZZY_THRESHOLD) -> list[MatchResult]:
        return [self.match(h, threshold=threshold) for h in header_texts]


def load_default_stores(data_dir: Path) -> tuple[DictionaryStore, DictionaryStore]:
    """Convenience loader for the two seed dictionaries shipped with this scaffold."""
    allow_store = DictionaryStore.load(data_dir / "allow_list.json", kind="allow")
    deny_store = DictionaryStore.load(data_dir / "deny_list.json", kind="deny")
    return allow_store, deny_store
