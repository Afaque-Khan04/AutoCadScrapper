# AutoCAD Structural Schedule Extraction Pipeline — Implementation Plan

## Goal

Build a Python pipeline that extracts structured data from **engineering schedule tables** (Beam Schedule, Slab Schedule, Column Schedule, etc.) embedded in AutoCAD-exported **vector PDFs**. Output is canonical JSON (CSV as a secondary export).

## Project Understanding

The pipeline works in 4 stages:
1. **Anchor Detection** — Find schedule titles (e.g. "SCHEDULE OF BEAMS") as entry points
2. **Grid Reconstruction** — Recover table structure from vector ruling lines (not OCR)
3. **Cell Extraction** — Map text into grid cells, parse rebar notation
4. **Normalization & Export** — Map headers to canonical fields, produce JSON/CSV

### Key Constraints (Explicit Non-Goals)
- ❌ No dimension-line / arrowhead / geometry-to-text detection
- ❌ No OCR / raster handling (vector-PDF-first)
- ❌ No FastAPI / Docker / .NET integration

---

## Existing Reference Code Analysis

The `reference/` folder contains 5 files generated from Claude, forming the Phase 1 baseline:

| File | Purpose | Status |
|------|---------|--------|
| [anchor_detection.py](file:///d:/Workspace/AutoCadScrapper/reference/anchor_detection.py) | Regex-based schedule title search → `ScheduleAnchor` objects | Solid baseline |
| [grid_reconstructor.py](file:///d:/Workspace/AutoCadScrapper/reference/grid_reconstructor.py) | Vector line extraction, collinear merging, grid building, merge detection | Core logic, needs real-PDF validation |
| [table_builder.py](file:///d:/Workspace/AutoCadScrapper/reference/table_builder.py) | Orchestrator: anchor → region clip → grid → cell text → output dict | Uses relative imports (package structure assumed) |
| [rebar_notation.py](file:///d:/Workspace/AutoCadScrapper/reference/rebar_notation.py) | Parses rebar shorthand (`4-T20`, `2-16Ø+1-12Ø`, `T10@150c/c`) | Clean, well-tested patterns |
| [schedule_schema_example.json](file:///d:/Workspace/AutoCadScrapper/reference/schedule_schema_example.json) | Target canonical JSON shape | Reference schema |

---

## Proposed Project Structure

```
d:\Workspace\AutoCadScrapper\
├── requirements.txt
├── README.md
├── src/
│   └── tables/
│       ├── __init__.py
│       ├── anchor_detection.py      # From reference (adapted)
│       ├── grid_reconstructor.py    # From reference (adapted)
│       ├── table_builder.py         # From reference (adapted)
│       ├── rebar_notation.py        # From reference (adapted)
│       └── header_normalizer.py     # [NEW] Phase 1 — fuzzy header mapping
├── tests/
│   ├── __init__.py
│   ├── test_anchor_detection.py
│   ├── test_grid_reconstructor.py
│   ├── test_rebar_notation.py
│   └── test_table_builder.py
├── schemas/
│   └── schedule_schema_example.json # From reference
├── benchmarks/                      # Place benchmark PDFs here
│   └── .gitkeep
├── output/                          # Generated JSON/CSV output
│   └── .gitkeep
└── reference/                       # Original Claude-generated files (kept as-is)
```

---

## Proposed Changes

### Phase 1 — Validate and Complete Core Vector Extraction

#### [NEW] `requirements.txt`
Core dependencies:
- `PyMuPDF` (fitz) — PDF vector/text extraction
- `rapidfuzz` — Fuzzy string matching for header normalization
- `pytest` — Testing framework

#### [NEW] `src/tables/__init__.py`
Package init to enable relative imports used in `table_builder.py`.

#### [MODIFY] `src/tables/anchor_detection.py`
Copy from reference, adapt if needed for package structure.

#### [MODIFY] `src/tables/grid_reconstructor.py`
Copy from reference, adapt if needed.

#### [MODIFY] `src/tables/table_builder.py`
Copy from reference. The relative imports (`.anchor_detection`, `.grid_reconstructor`, `.rebar_notation`) will work with the `src/tables/` package structure.

#### [MODIFY] `src/tables/rebar_notation.py`
Copy from reference as-is.

#### [NEW] `src/tables/header_normalizer.py`
- Fuzzy-match raw headers to canonical field names via alias dictionary
- Uses `rapidfuzz` for matching (threshold-based)
- Handles parent-header relationships for merged cells

#### [NEW] `tests/test_rebar_notation.py`
Unit tests for all rebar notation variants including compound `+` cases.

#### [NEW] `tests/test_anchor_detection.py`
Unit tests for anchor detection with mocked PyMuPDF page objects.

---

## User Review Required

> [!IMPORTANT]
> **Benchmark PDF Required**: Phase 1 requires a real benchmark PDF containing Schedule of Beams and Schedule of Slabs to validate the pipeline. Do you have one available to place in `benchmarks/`?

> [!IMPORTANT]
> **Project Structure**: The plan places source code under `src/tables/` (matching the relative imports in `table_builder.py`). Is this structure acceptable, or do you prefer a different layout?

## Open Questions

1. **Python version**: The prompt specifies Python 3.11+. Should I target the exact Python version installed on your system? (I'll check during venv creation.)

2. **Header alias dictionary**: The `header_normalizer.py` needs a mapping of known header text variations → canonical field names. Should I build an initial dictionary from the schema example and the patterns mentioned in the prompt, or do you have a reference list of header variants from your actual drawings?

3. **Phase execution**: The prompt says to work strictly phase-by-phase. Should I set up the full project structure now (folders, requirements, venv) and then wait for a benchmark PDF before executing Phase 1 code? Or should I proceed with writing all Phase 1 code now and we test when a PDF is available?

---

## Verification Plan

### Automated Tests
```bash
# Run all tests
pytest tests/ -v

# Run specific module tests
pytest tests/test_rebar_notation.py -v
pytest tests/test_anchor_detection.py -v
```

### Manual Verification
- Run `python -m src.tables.table_builder <benchmark.pdf>` against a real PDF
- Inspect output JSON for correct table structure, merged headers, and rebar parsing
- Visual verification of detected grid regions against the source PDF
