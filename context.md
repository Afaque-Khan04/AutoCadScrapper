# AutoCAD Structural Schedule & Notes Extractor — Project Context

## Project Overview & Scope

The goal of this project is to automatically extract structured data from AutoCAD-exported vector PDF engineering drawings.
This includes:
1. **Schedule Tables**: Structural schedules (Beam, Slab, Column, Bar Bending / BBS, Material / BOM) and Mould Drawing schedules (Weight, Insert, Dowel Bar).
2. **Non-Schedule Panels**: General Notes, Legends, Specifications, and metadata panels.

The final output is a canonical, JSON-serializable structure with normalized field names, parsed rebar notations, and key-value pairings.

---

## Architectural Summary

The codebase implements a **hybrid, multi-strategy extraction pipeline**:

```
                    ┌──────────────────────────┐
                    │  Anchor Detection        │
                    │  (Regex title matching)  │
                    └──────────┬───────────────┘
                               │
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
   [ region_type == "schedule" ]        [ region_type == "general_notes" ]
            │                                     │
    ┌───────┴───────┐                             ▼
    ▼               ▼                     ┌───────────────┐
Strategy A     Strategy B                 │  Notes        │
Vector Grid    Text Clustering            │  Parser       │
Recon.         Fallback                   └───────┬───────┘
    │               │                             │
    └───────┬───────┘                             │
            ▼                                     │
   Header Normalizer + Rebar Parser               │
            │                                     │
            └──────────────────┬──────────────────┘
                               ▼
                      Canonical JSON Output
```

### Module Responsibilities

1. **`src/tables/anchor_detection.py`**
   - Scans PDF text for title patterns defined in `src/utils/constants.py`.
   - Returns `ScheduleAnchor` objects containing `table_type`, `bbox`, `page_number`, and `region_type` (`"schedule"`, `"general_notes"`, `"legend"`, `"specifications"`).
   - Uses `SCHEDULE_TITLE_EXCLUSIONS` to ignore title-block blocks like `REVISION SCHEDULE`.

2. **`src/tables/grid_reconstructor.py`** (Strategy A — Vector Grid)
   - Extracts vector ruling lines via PyMuPDF `get_drawings()`.
   - Clusters collinear lines into row/column boundaries and builds `TableGrid` cells.
   - Detects horizontally merged header cells.

3. **`src/tables/text_clustering.py`** (Strategy B — Text-Only Fallback)
   - Handles schedule tables with ZERO vector ruling lines.
   - Clusters text words into rows (`ROW_TOLERANCE = 6.0`) and columns (`CELL_GAP_THRESHOLD = 8.0`).
   - Filters columns by proximity to the anchor title (`ANCHOR_PROXIMITY_MULTIPLIER = 1.2`).

4. **`src/parsing/notes_parser.py`** (General Notes & Legends)
   - Vector-bounded region discovery with title block exclusion (`CLIENT:`, `PROJECT:`, `REVISION SCHEDULE`, `STRUCTURAL CONSULTANT`).
   - Deduplicates overlaid CAD word tokens.
   - Parses single & multi-line keys (e.g. `LIFTING,TRANSPORTATION AND ERECTION - M35`).
   - Parses nested sub-sections (e.g. `COVER: COLUMN - 40mm`).
   - Parses standalone metadata statements (e.g. `ALL DIMENSIONS ARE IN MM`).

5. **`src/tables/header_normalizer.py` & `src/parsing/rebar_notation.py`**
   - Fuzzy-matches raw headers against `HEADER_ALIASES` in `constants.py` using `rapidfuzz` (threshold: 70).
   - Parses compound rebar shorthand strings (e.g. `2-T20@200 + 3-T16@150`).

6. **`src/tables/table_builder.py`** (Orchestrator)
   - `extract_all_tables(pdf_path)`: Returns schedule table dictionaries.
   - `extract_all_regions(pdf_path)`: Returns all regions (schedules, notes, legends) with anchor-containment deduplication to prevent duplicate extractions.

---

## Current Status & Achievements

- **Test Suite**: **90/90 unit & integration tests passing** (`pytest tests/`).
- **Benchmark Execution**: Tested against `reference/benchmarkpdf.pdf`. Produces 4 non-overlapping regions:
  1. `general_notes`:
     - `grade_of_concrete`: `"M50"`
     - `grade_of_steel`: `"Fe500"`
     - `stripping_strength`: `"M25"`
     - `liftingtransportation_and_erection`: `"M35"`
     - `cover`: `{"column": "40mm"}`
     - `legends`: `{"erection_mark": ""}`
     - `metadata`: `["ALL DIMENSIONS ARE IN MM"]`
     - *`CLIENT` block and `PROJECT: SIFY BANGALORE` are 100% excluded.*
  2. `weight_schedule`: 2 cols × 1 row (`Volume`, `Weight`).
  3. `insert_schedule`: 3 cols × 3 rows (`Ref No.`, `Type`, `Count`).
  4. `dowel_bar_schedule`: 3 cols × 3 rows (`Ref No Bar`, `Diameter`, `Count`).

---

## Project Structure

```
d:\Workspace\ACS\AutoCadScrapper\
├── requirements.txt
├── venv/                           # Virtual environment (Python 3.14)
├── reference/
│   └── benchmarkpdf.pdf            # Benchmark test PDF
├── src/
│   ├── __init__.py
│   ├── models/
│   │   └── __init__.py             # Dataclasses (TableGrid, ScheduleAnchor, etc.)
│   ├── parsing/
│   │   ├── __init__.py
│   │   ├── notes_parser.py         # General Notes & Legends parser
│   │   └── rebar_notation.py       # Rebar shorthand parser
│   ├── tables/
│   │   ├── __init__.py
│   │   ├── anchor_detection.py     # Anchor detector (schedules & notes)
│   │   ├── grid_reconstructor.py   # Vector grid builder
│   │   ├── header_normalizer.py    # Fuzzy header mapper
│   │   ├── table_builder.py        # Pipeline orchestrator
│   │   └── text_clustering.py      # Spatial text clustering fallback
│   └── utils/
│       ├── __init__.py
│       └── constants.py            # Title patterns, header aliases, exclusions
└── tests/
    ├── test_anchor_detection.py    # 11 tests
    ├── test_grid_reconstructor.py  # 8 tests
    ├── test_header_normalizer.py   # 12 tests
    ├── test_notes_parser.py        # 6 tests
    ├── test_rebar_notation.py      # 12 tests
    ├── test_table_builder.py       # 9 integration tests
    └── test_text_clustering.py     # 18 tests
```

---

## How to Run & Test

```bash
# Activate venv
.\venv\Scripts\activate

# Run full test suite (86 tests)
python -m pytest tests/ -v

# Run extraction on a PDF (CLI output)
python -m src.tables.table_builder reference\benchmarkpdf.pdf
```

---

## Roadmap / Next Steps

1. **Phase 3 — Beam & Slab Schedule Enhancements**:
   - Hierarchical multi-row header reconstruction (e.g. `BOTTOM REINFORCEMENT -> STRAIGHT / BENT`).
   - Adaptive word gap & row height thresholds based on page median metrics.
2. **Phase 4 — Confidence-Based Strategy Selection**:
   - Score Vector Grid vs Text Clustering outputs using header completeness and row alignment.
3. **Phase 5 — Ingestion & Exporters**:
   - Production CLI / API dispatcher, CSV / Excel exporters, Streamlit review UI.
