src/
├── ingestion/                 # unchanged: pdf_loader, dispatcher
├── extractors/
│   └── pdf/
│       ├── geometry_extractor.py   # reused — now pulls grid lines, not dimension lines
│       ├── text_extractor.py       # reused — cell text instead of dimension text
│       └── metadata_extractor.py   # reused — title block / page size
│
├── tables/                     # NEW — replaces analysis/*
│   ├── anchor_detection.py     # keyword search -> table_type + anchor bbox
│   ├── grid_reconstructor.py   # Option A: vector-line grid + merged-header detection
│   ├── text_clustering.py      # Option B: fallback when no usable grid found
│   ├── table_builder.py        # ties anchor + grid + text into one table object
│   └── header_normalizer.py    # raw header -> canonical field (fuzzy match against a lookup dict)
│
├── parsing/                    # repurposed — rebar/BOM notation, not tolerance grammar
│   ├── rebar_notation.py       # "4-T20", "T10@150c/c" -> structured fields
│   └── value_normalizer.py
│
├── models/                     # Table, TableHeader, TableRow, Cell (replaces Dimension/Geometry)
├── validation/                 # confidence scoring, review queue — unchanged in spirit
├── exporters/                  # json/csv/debug — debug overlay of detected grid is very worth keeping
├── ui/                         # Streamlit review app — unchanged in spirit
└── utils/                      # + constants.py now holds schedule-title keywords & header aliases