# ACS — Streamlit Review UI Runbook

How to run the Streamlit review/demo UI for the AutoCAD Schedule Extractor
and how to obtain its output (JSON). This is the **demo/review tool** from the
"Prompt for ui" milestone — **not** the planned Phase 5 production UI.

Everything below runs from the **AutoCadScrapper** directory (the canonical
repo, `D:\Workspace\ACS\AutoCadScrapper`).

---

## 1. Prerequisites

- **Python 3.14** virtual environment already exists at `AutoCadScrapper\venv\`.
- If dependencies are missing (e.g. after a fresh clone), install them once:

  ```bash
  cd AutoCadScrapper
  .\venv\Scripts\python.exe -m pip install -r requirements.txt
  ```

  `requirements.txt` includes the extraction pipeline (PyMuPDF, rapidfuzz),
  testing (pytest), and **streamlit** for the UI.

## 2. Run the app

```bash
cd AutoCadScrapper
.\venv\Scripts\python.exe -m streamlit run src\ui\streamlit_app.py
```

- Streamlit opens the app in your default browser at `http://localhost:8501`.
- To use a different port (e.g. if 8501 is busy): add `--server.port 8502`.
- Headless/remote start (no browser launch):

  ```bash
  .\venv\Scripts\python.exe -m streamlit run src\ui\streamlit_app.py --server.headless true
  ```

## 3. Using the app

1. **Input PDF** (sidebar):
   - Upload an AutoCAD-exported **vector** PDF via the file picker, **or**
   - Click **"Try the bundled benchmark PDF"** to load `reference\benchmarkpdf.pdf`
     for an instant demo (no upload needed).
2. The pipeline runs once per document (`extract_all_regions`); a spinner is
   shown while it works, and a green banner reports how many regions were found.
3. **Summary metrics** at the top: region count, schedule tables vs. notes
   panels, and how many tables came from vector grid reconstruction vs.
   text clustering.
4. Pick a **region** from the dropdown (e.g. GENERAL NOTES, Weight Schedule,
   Insert Schedule, Dowel Bar Schedule).
5. **Tabs** per region:
   - **Review view** — reviewer-friendly output: a rendered table for
     schedules, JSON for notes panels, plus the raw presentation JSON.
   - **Canonical JSON** — the full engineering/audit JSON (bboxes, confidence,
     normalized rebar values, merged-header info, `detection_strategy`).
6. **Download buttons**:
   - Per region: *Download region JSON* (canonical and simplified variants).
   - Sidebar → *Export full document*: `<stem>_canonical.json` and
     `<stem>_simplified.json` for the whole document.

## 4. Getting output without the UI (CLI)

The UI is a thin wrapper over the same pipeline, so the JSON it downloads is
identical to what these commands produce:

```bash
# 1) Print canonical JSON for all regions to stdout
.\venv\Scripts\python.exe -m src.tables.table_builder reference\benchmarkpdf.pdf

# 2) Write BOTH tiers to output/ as files
.\venv\Scripts\python.exe -m src.exporters.presentation_exporter reference\benchmarkpdf.pdf
```

The exporter writes:

| File                          | Contents                                              |
|-------------------------------|-------------------------------------------------------|
| `output\<stem>_canonical.json`  | Full canonical JSON (engineering/audit format)        |
| `output\<stem>_simplified.json` | Reviewer-friendly presentation JSON                   |

`output\benchmarkpdf_canonical.json` / `output\benchmarkpdf_simplified.json`
are the committed reference outputs for the benchmark PDF — regenerate them
with command (2) if the pipeline ever changes.

## 5. Tests

```bash
cd AutoCadScrapper
.\venv\Scripts\python.exe -m pytest tests\ -q
```

107 tests cover the pipeline, the exporter, the new shared text-geometry
module, and the grid-provenance (`source`) fix.

## 6. Type checking (pyright)

Pyright is configured at the workspace root (`pyrightconfig.json`, scoped to
`AutoCadScrapper/src` + `AutoCadScrapper/tests` with the venv interpreter):

```bash
cd D:\Workspace\ACS
npx --yes pyright
```

Expected result: `0 errors, 0 warnings, 0 informations`.

## 7. Troubleshooting

- **"Extraction failed — Failed to open file ... as type pdf"** — the upload is
  not a readable PDF (e.g. a scanned image or a corrupt file). The pipeline
  needs AutoCAD-exported **vector** PDFs with embedded text; it does not OCR.
- **"No schedule regions were detected..."** — the PDF loaded but contains no
  schedule/notes titles the anchor detector recognises.
- **Port already in use** — start with `--server.port <other>`.
- **ModuleNotFoundError: streamlit** — run the pip install step from
  section 1.
