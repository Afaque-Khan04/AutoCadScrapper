# Phase 2.5 Walkthrough — General Notes & Legends Extraction

## What Was Built

Implemented Phase 2.5 support for **General Notes**, **Legends**, and non-schedule engineering drawing panels while strictly preserving the existing hybrid vector/text pipeline.

```
d:\Workspace\ACS\AutoCadScrapper\
├── src/
│   ├── utils/
│   │   └── constants.py            # Added NOTES_TITLE_PATTERNS (general_notes, legend, specifications)
│   ├── tables/
│   │   ├── anchor_detection.py     # Extended with region_type field and find_all_anchors
│   │   └── table_builder.py        # Added region_type routing & extract_all_regions entry point
│   ├── parsing/
│   │   ├── notes_parser.py         # [NEW] Vector-bounded General Notes & Legends parser
│   │   └── rebar_notation.py
│   └── models/
├── tests/
│   ├── test_anchor_detection.py    # 11 tests
│   ├── test_grid_reconstructor.py  # 8 tests
│   ├── test_header_normalizer.py   # 12 tests
│   ├── test_notes_parser.py        # [NEW] 6 tests (General Notes integration & unit tests)
│   ├── test_rebar_notation.py      # 12 tests
│   ├── test_table_builder.py       # 9 integration tests
│   └── test_text_clustering.py     # 18 tests
```

---

## Key Features & Logic

### 1. Vector-Bounded Region Discovery (`notes_parser.py`)
- Discovers the exact vector boundary lines framing the General Notes box (in benchmark PDF: `x=[951.2, 1163.5]`, `y=[67.9, 402.6]`).
- Trims `bottom_y` before title block metadata keywords (e.g., `CLIENT:`, `PROJECT:`, `REVISION SCHEDULE`, `STRUCTURAL CONSULTANT`).
- **Explicitly excludes `CLIENT` and surrounding title block boxes** (which start at `y=415.8`).

### 2. Multi-Line Key & Nested Section Parsing
- Assembles multi-line keys (e.g., `LIFTING,TRANSPORTATION AND ERECTION - M35`).
- Parses nested subsections (e.g. `COVER: COLUMN - 40mm` mapped under `cover.column`).
- Extracts standalone metadata statements (e.g. `ALL DIMENSIONS ARE IN MM`).
- Normalizes raw key text to canonical `snake_case` keys.

---

## Test Results

```
86 passed in 11.52s
```

| Test File | Tests | Status |
|-----------|-------|--------|
| `test_anchor_detection.py` | 11 | ✅ All pass |
| `test_grid_reconstructor.py` | 8 | ✅ All pass |
| `test_header_normalizer.py` | 12 | ✅ All pass |
| `test_notes_parser.py` | 6 | ✅ All pass (Phase 2.5) |
| `test_rebar_notation.py` | 12 | ✅ All pass |
| `test_table_builder.py` | 9 | ✅ All pass |
| `test_text_clustering.py` | 18 | ✅ All pass |

---

## Benchmark PDF Extraction Summary

Running `python -m src.tables.table_builder reference\benchmarkpdf.pdf` extracts 5 structured regions:

1. **`general_notes`**:
   - `grade_of_concrete`: `"M50"`
   - `grade_of_steel`: `"Fe500"`
   - `stripping_strength`: `"M25"`
   - `liftingtransportation_and_erection`: `"M35"`
   - `cover`: `{"column": "40mm"}`
   - `metadata`: `["ALL DIMENSIONS ARE IN MM"]`
2. **`legend`**: Extracted section header & erection mark.
3. **`weight_schedule`**: 2 cols × 1 row (`Volume`, `Weight`).
4. **`insert_schedule`**: 3 cols × 3 rows (`Ref No.`, `Type`, `Count`).
5. **`dowel_bar_schedule`**: 3 cols × 3 rows (`Ref No Bar`, `Diameter`, `Count`).

*CLIENT box (below y=410) is completely excluded.*
