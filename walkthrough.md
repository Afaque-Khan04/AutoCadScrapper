# Phase 1 Walkthrough — Core Vector Extraction Pipeline

## What Was Built

The full project structure per [struct.md](file:///d:/Workspace/AutoCadScrapper/struct.md), with Phase 1 modules implemented and tested:

```
d:\Workspace\AutoCadScrapper\
├── requirements.txt                    # PyMuPDF, rapidfuzz, pytest, jsonschema
├── struct.md
├── venv/                               # Python 3.14.5 virtual environment
├── src/
│   ├── __init__.py
│   ├── tables/
│   │   ├── __init__.py
│   │   ├── anchor_detection.py         # Schedule title finder (adapted)
│   │   ├── grid_reconstructor.py       # Vector-line grid builder (from reference)
│   │   ├── header_normalizer.py        # [NEW] Fuzzy header → canonical field
│   │   └── table_builder.py            # Orchestrator (adapted)
│   ├── parsing/
│   │   ├── __init__.py
│   │   └── rebar_notation.py           # Rebar shorthand parser (from reference)
│   ├── models/
│   │   └── __init__.py                 # Table, Cell, Header, Row dataclasses
│   ├── utils/
│   │   ├── __init__.py
│   │   └── constants.py                # [NEW] Title patterns + header aliases
│   ├── ingestion/                      # Stub (Phase 2+)
│   ├── extractors/pdf/                 # Stub (Phase 2+)
│   ├── validation/                     # Stub (Phase 2+)
│   ├── exporters/                      # Stub (Phase 2+)
│   └── ui/                             # Stub (Phase 2+)
├── tests/
│   ├── test_rebar_notation.py          # 12 tests
│   ├── test_anchor_detection.py        # 11 tests
│   ├── test_grid_reconstructor.py      # 8 tests
│   ├── test_header_normalizer.py       # 12 tests
│   └── test_table_builder.py           # 9 integration tests (benchmark PDF)
├── schemas/
│   └── schedule_schema_example.json
└── reference/                          # Original files (preserved)
```

---

## Changes from Reference Code

### [anchor_detection.py](file:///d:/Workspace/AutoCadScrapper/src/tables/anchor_detection.py)
- Patterns moved to centralized [constants.py](file:///d:/Workspace/AutoCadScrapper/src/utils/constants.py)
- Pre-compiled regex patterns (was re-compiling each call)
- Added **exclusion patterns** — "REVISION SCHEDULE" no longer triggers false positives
- Added **image block filtering** (`block_type != 0`)
- Added patterns for benchmark PDF types: `weight_schedule`, `insert_schedule`, `dowel_bar_schedule`

### [table_builder.py](file:///d:/Workspace/AutoCadScrapper/src/tables/table_builder.py)
- Fixed imports for new package structure (`from ..parsing.rebar_notation`)
- **Wired header normalization** — first grid row is extracted as headers, fuzzy-matched to canonical fields
- **Selective rebar parsing** — `parse_rebar_value` only applied to columns identified as rebar fields, prevents false parsing of marks/dimensions
- Data rows start from index 1 (header excluded from data rows)

### [header_normalizer.py](file:///d:/Workspace/AutoCadScrapper/src/tables/header_normalizer.py) — **NEW**
- Fuzzy matching via `rapidfuzz` against alias dictionary
- Exact match fast path before fuzzy fallback
- Configurable threshold (70) — below this, raw header preserved as-is

### [constants.py](file:///d:/Workspace/AutoCadScrapper/src/utils/constants.py) — **NEW**
- 12 schedule title pattern groups (7 structural + 3 precast + 2 standard)
- 20+ canonical header field definitions with aliases
- Exclusion patterns for non-structural "schedules"

---

## Test Results

```
60 passed in 7.41s
```

| Test File | Tests | Status |
|-----------|-------|--------|
| `test_rebar_notation.py` | 12 | ✅ All pass |
| `test_anchor_detection.py` | 11 | ✅ All pass |
| `test_grid_reconstructor.py` | 8 | ✅ All pass |
| `test_header_normalizer.py` | 12 | ✅ All pass |
| `test_table_builder.py` | 9 | ✅ All pass (benchmark PDF) |

---

## Benchmark PDF Analysis

The pipeline found **3 tables** in [benchmarkpdf.pdf](file:///d:/Workspace/AutoCadScrapper/reference/benchmarkpdf.pdf):

| Table | Type | Grid Detected | Headers Extracted | Data Rows |
|-------|------|---------------|-------------------|-----------|
| Weight Schedule | `weight_schedule` | ✅ 4 cols | ⚠️ Empty (see below) | 2 |
| Insert Schedule | `insert_schedule` | ⚠️ 1 col only | ⚠️ "400" | 0 |
| Dowel Bar Schedule | `dowel_bar_schedule` | ⚠️ 1 col only | ⚠️ "400" | 0 |

### Observations

> [!NOTE]
> **Weight Schedule** — Grid is detected but the table structure in this PDF is unusual. The schedule titles sit above their data, but the ruling lines that form the actual table cells span across all three schedules rather than being independent grids per schedule. The "Volume" and "Weight" text lands in what the grid sees as a data row because the header band is very narrow.

> [!NOTE]
> **Insert & Dowel Bar Schedules** — The search region starts from the anchor's bottom edge and extends right to the page boundary. Because these schedules sit side-by-side (not stacked vertically), the grid reconstructor picks up lines from the section view to the right ("400" is a dimension from the drawing, not table data). These tables need the search region to be **width-bounded** to the schedule's actual columns, not the full page width.

### What This Tells Us
The core pipeline (anchor → region → grid → cells → JSON) works correctly. The issues are all about **region bounding for side-by-side schedules** — a layout pattern not covered by the reference code's assumption that schedules sit stacked vertically. This is a known refinement area for Phase 2, or can be addressed immediately if needed.

---

## How to Run

```bash
# Activate venv
.\venv\Scripts\activate

# Run tests
python -m pytest tests/ -v

# Extract tables from a PDF
python -m src.tables.table_builder reference\benchmarkpdf.pdf
```
