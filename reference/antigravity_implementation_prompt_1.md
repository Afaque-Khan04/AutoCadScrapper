# Project Brief: AutoCAD Structural Schedule Extraction Pipeline

## Goal

Build a Python pipeline that extracts structured data from **engineering
schedule tables** (Beam Schedule, Slab Schedule, Column Schedule,
Reinforcement Schedule, Bar Bending Schedule, Material Schedule, Bill of
Materials) embedded in AutoCAD-exported **vector PDFs**. Output is
canonical JSON (CSV as a secondary export).

## Explicit non-goals

Do NOT build dimension-line detection, arrowhead detection, or
geometry-to-text association for measurement dimensions. That was an
earlier direction for this project and has been abandoned. The layout
drawing on a sheet (beam layout, slab layout, etc.) is context only —
we do not extract anything from it except the schedule tables sitting
alongside it.

Do NOT build OCR/raster handling yet — this is vector-PDF-first.
Raster fallback is a later, separate phase and should not be started
until explicitly requested.

Do NOT build a FastAPI service, Docker container, or any .NET-facing
integration layer yet. This is a Python-only proof of concept for now;
integration work comes later and is out of scope until told otherwise.

## Source material characteristics (confirmed against real benchmark drawings)

- PDFs are vector-plotted from AutoCAD — table borders are real ruled
  lines (vector paths), not just visual whitespace gaps. Grid
  reconstruction from vector geometry should be the **primary**
  detection strategy; text-position clustering is a fallback only.
- Schedule tables are consistently labeled with a title directly above
  them: "SCHEDULE OF BEAMS", "SCHEDULE OF SLABS", "SCHEDULE OF SLAB
  BEAM(SB)", etc. Use these as search anchors rather than scanning the
  whole page for table-like regions.
- Headers are frequently two-row with merges in BOTH directions:
  - horizontal merge: a parent label spanning multiple sub-columns
    (e.g. "BOTTAM REINFO." spanning "STR." / "BENT")
  - vertical merge: a column with no sub-columns, spanning the full
    header height while its neighbors split into two rows (e.g. "BEAM
    MKD." next to a two-row reinforcement group)
- Reinforcement/rebar notation varies and can be **compound** within a
  single cell:
  - `4-T20` (count-dash-bar_type)
  - `2-16Ø` (count-dash-diameter with a diameter symbol)
  - `2-16Ø+1-12Ø` — TWO bar groups in one cell, joined by `+`
  - `T10@150c/c` (bar_type-at-spacing)
  - `6Ø130C/C` (diameter and spacing with no separator between them)
- A detail drawing (e.g. "General Section of Beam") can sit directly
  below a schedule table on the same sheet. Table-region bounding must
  stop at the actual end of the ruled grid (detected via row-to-row
  gap analysis), not a fixed pixel height, or the detail drawing's
  lines will get swept into the table.
- Some sheets are authored landscape and rendered rotated. PyMuPDF is
  expected to apply the page's `/Rotate` transform automatically to
  both text and vector-path extraction, but this has NOT yet been
  verified against a real rotated benchmark PDF — treat as an open
  risk to test early, not a settled assumption.
- Later phase (do not build yet): Bar Bending Schedule tables may
  contain a column with an actual drawn bent-bar shape sketch rather
  than text. If a text shape-code is present alongside the sketch,
  that's a simple text field. If there is only the rendered sketch
  with no code, that one column needs scoped vector-geometry
  extraction — this is the one legitimate exception to "no geometry
  work" in this project, and only applies to that specific column type,
  only in Phase 4.

## Existing code (already written — use as the Phase 1 starting point)

The following modules already exist and should be treated as the
working baseline, not rewritten from scratch. Read them fully before
making changes; extend or fix rather than replace unless something is
actually broken against real test data:

- `tables/anchor_detection.py` — keyword search for schedule titles,
  returns `ScheduleAnchor` objects with `table_type` + bbox.
- `tables/grid_reconstructor.py` — vector-line grid reconstruction,
  including both horizontal- and vertical-merge header detection.
- `tables/table_builder.py` — ties anchor detection + grid
  reconstruction + cell text extraction + rebar parsing into one
  canonical table dict per detected schedule. Includes content-gap-based
  region bounding (not fixed-height).
- `tables/rebar_notation.py` — parses rebar/reinforcement shorthand,
  including compound `+`-joined groups, into structured field lists.
- `schedule_schema_example.json` — target canonical JSON shape
  (`document` → `tables[]` → `headers[]` + `rows[].cells[]`, with
  `raw_text` preserved alongside `normalized_value` for every cell).

These files are attached alongside this prompt. Load and review them
before writing new code.

## How to work: strictly incremental, phase by phase

Do not implement multiple phases in one pass. After each phase:
1. Run the code against the attached benchmark PDF(s).
2. Report what worked, what didn't, and any assumption you had to make
   that wasn't specified here.
3. Wait for explicit go-ahead before starting the next phase.

### Phase 1 — Validate and complete the core vector extraction (start here)

- Run the existing `tables/table_builder.py` against a real benchmark
  PDF containing a Schedule of Beams and Schedule of Slabs.
- Fix whatever breaks against real PyMuPDF output (e.g.
  `get_drawings()` item structure, exact line-type codes — these can
  vary slightly by PDF producer and haven't been verified against a
  real file yet).
- Confirm merged-header detection (both directions) produces correct
  `parent_header` relationships once wired into a `header_normalizer.py`
  (build this now if not already present — fuzzy-match raw headers to
  canonical field names via a maintained alias dictionary; use
  `rapidfuzz` or similar rather than exact string matching, since
  header wording varies by drafter).
- Confirm rebar-notation parsing produces correct `normalized_value`
  output on real cell text, including the compound `+` case.
- Write `pytest` tests against the benchmark file(s) for: anchor
  detection, grid reconstruction, merge detection, and rebar parsing.
- Do NOT move on to Phase 2 until this produces clean, correct JSON on
  at least one real Beam Schedule + Slab Schedule sheet.

### Phase 2 — Normalization, validation, and export (only after Phase 1 is confirmed working)

- `header_normalizer.py` if not finished in Phase 1.
- Confidence scoring / consistency checks (row length consistency,
  expected-column-count sanity per `table_type`).
- Review-queue construction: flag tables/cells that fail a confidence
  or consistency check, with a human-readable reason.
- CSV exporter (flatten canonical JSON to spreadsheet-friendly rows).
- Debug exporter: render the detected grid, anchor, and merged-header
  regions as an overlay on a rasterized copy of the source page, for
  visual QA.

### Phase 3 — Fallback path and robustness (only after Phase 2 is confirmed working)

- `text_clustering.py`: column/row reconstruction from text position
  when no usable grid is found (fewer than 2 rows/cols detected).
- Multi-page / continuation-table handling (e.g. "Schedule of Beams
  (Contd.)" on a following sheet).
- Extend `anchor_detection.py`'s keyword patterns to cover Column
  Schedule, Material Schedule, and Bill of Materials once you have real
  examples of each.

### Phase 4 — Bar Bending Schedule and any raster fallback (only if/when explicitly requested)

Do not start this phase speculatively. Wait for a real BBS benchmark
file and explicit instruction before touching the shape-sketch column
or building any raster/OCR path.

## Conventions to follow

- Python 3.11+, type hints throughout, dataclasses for structured
  intermediate objects (matching the existing files' style).
- Docstrings should explain *why*, not just what — the existing files
  document the real-world reasoning behind each design choice (e.g.
  why anchors are keyword-based, why merge detection works off missing
  rulings); keep that standard for new code.
- Every raw extracted value should be preserved alongside its
  normalized/parsed form — never discard the original text.
- Confidence should be tracked per cell/table even though vector text
  extraction is exact (constant high confidence) now, since the same
  schema needs to accommodate OCR-derived confidence once a raster path
  exists.
