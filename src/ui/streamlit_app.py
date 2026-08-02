"""
Streamlit review/demo UI for the AutoCAD Schedule Extractor (ACS).

This is a DEMO / REVIEW tool (the "Prompt for ui" milestone), NOT the
planned Phase 5 production UI. It wraps the existing extraction
pipeline — ``src.tables.table_builder.extract_all_regions`` plus the
presentation exporter's ``simplify_for_presentation`` — and adds no
extraction logic of its own.

Workflow:
  1. Upload an AutoCAD-exported vector PDF (or load the bundled
     benchmark PDF from the sidebar for a quick demo).
  2. The pipeline runs once per document; results are cached in
     ``st.session_state`` for the browser session.
  3. Browse regions (General Notes, Weight/Insert/Dowel Bar Schedules,
     …) via the selector, view each tier (review-friendly presentation
     JSON and full canonical JSON), and download either tier for the
     selected region or for the whole document.

Run from the AutoCadScrapper repo root:

    .\\venv\\Scripts\\activate
    streamlit run src/ui/streamlit_app.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

# Allow `src.*` imports regardless of how the app is launched
# (mirrors what the test suite does).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st  # noqa: E402

from src.tables.table_builder import extract_all_regions  # noqa: E402
from src.exporters.presentation_exporter import simplify_for_presentation  # noqa: E402

BENCHMARK_PDF = PROJECT_ROOT / "reference" / "benchmarkpdf.pdf"

NOTES_TYPES = {"general_notes", "legend", "specifications"}

STRATEGY_LABELS = {
    "vector": ("Vector grid reconstruction", "🟦"),
    "text_clustering": ("Text clustering", "🟩"),
    "notes": ("Notes parser (non-table)", "🟨"),
    "n/a": ("Not exposed", "⬜"),
}


def _to_json(obj) -> str:
    """Compact helper: pretty-printed, UTF-8-safe JSON string."""
    return json.dumps(obj, indent=2, ensure_ascii=False)


def _region_name(region: dict) -> str:
    """Human-friendly region name (first line of the title, colon stripped)."""
    raw = region.get("title_raw") or ""
    if raw:
        return raw.splitlines()[0].strip().rstrip(":")
    return region.get("table_type", "Region")


def _is_notes(region: dict) -> bool:
    return (
        region.get("table_type") in NOTES_TYPES
        or region.get("region_type") in NOTES_TYPES
        or "general_notes" in region
    )


def _strategy_of(region: dict) -> str:
    if _is_notes(region):
        return "notes"
    return region.get("detection_strategy", "n/a")


def _render_strategy_badge(region: dict) -> None:
    """Small colored chip describing how this region was extracted."""
    key = _strategy_of(region)
    label, icon = STRATEGY_LABELS.get(key, ("Unknown", "❔"))
    st.markdown(
        f"<span style='background:#0b4f5e;color:#e6f7f9;padding:2px 10px;"
        f"border-radius:12px;font-size:0.85em'>{icon}&nbsp;{label}</span>",
        unsafe_allow_html=True,
    )


def _render_region_diagnostics(region: dict) -> None:
    """Expander with the audit-style details of a region."""
    with st.expander("Region diagnostics", expanded=False):
        st.markdown(
            "**Table type:** `{}`  \n"
            "**Page:** {}  \n"
            "**Detection strategy:** `{}`  \n"
            "**Rows / columns:** {} / {}  \n"
            "**Merged header cells:** {}  \n"
            "**Source region bbox:** `{}`".format(
                region.get("table_type", "—"),
                region.get("page_number", "—"),
                region.get("detection_strategy", "n/a"),
                region.get("row_count", "—"),
                region.get("col_count", "—"),
                len(region.get("merged_header_cells", [])),
                region.get("source_region_bbox", "—"),
            )
        )


def _render_review_tab(region: dict, simplified_entry: dict, stem: str, idx: int) -> None:
    """Reviewer-friendly view: rendered table (schedules) or JSON (notes),
    plus the raw presentation JSON and a per-region download button."""
    st.subheader(_region_name(region))

    if "rows" in simplified_entry:
        rows = simplified_entry.get("rows") or []
        st.caption(f"{len(rows)} data row(s)")
        if rows:
            st.dataframe(rows, width="stretch", hide_index=True)
        else:
            st.info("No data rows were extracted for this table.")
    else:
        st.json(simplified_entry)

    with st.expander("Raw presentation JSON"):
        st.json(simplified_entry)
    st.download_button(
        "Download region JSON",
        data=_to_json(simplified_entry),
        file_name=f"{stem}_region{idx + 1}_simplified.json",
        mime="application/json",
        key=f"dl_simplified_{idx}",
    )


def _render_canonical_tab(region: dict, stem: str, idx: int) -> None:
    """Full canonical JSON (engineering/audit format) for the region."""
    st.json(region)
    st.download_button(
        "Download region JSON",
        data=_to_json(region),
        file_name=f"{stem}_region{idx + 1}_canonical.json",
        mime="application/json",
        key=f"dl_canonical_{idx}",
    )


def _extract(pdf_path: str):
    """Runs the pipeline (throwing exceptions up to the caller)."""
    return extract_all_regions(pdf_path)


def main() -> None:
    st.set_page_config(
        page_title="ACS Schedule Extractor — Review UI",
        page_icon="📐",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("📐 AutoCAD Schedule Extractor")
    st.caption(
        "Review/demo tool — upload an AutoCAD-exported vector PDF and inspect the "
        "extracted schedules & notes in both presentation and canonical JSON form."
    )

    # ------------------------------------------------------------------
    # Sidebar: input source + full-document export
    # ------------------------------------------------------------------
    with st.sidebar:
        st.header("1 · Input PDF")
        uploaded = st.file_uploader(
            "Upload a vector PDF",
            type=["pdf"],
            help="AutoCAD-exported PDFs with embedded text (no scanned images).",
        )
        use_benchmark = st.button(
            "Try the bundled benchmark PDF",
            help=f"Loads {BENCHMARK_PDF.name} from the repo's reference/ folder.",
            width="stretch",
        )

        st.divider()
        st.header("2 · Export full document")

    # ------------------------------------------------------------------
    # Resolve the active source (upload vs benchmark). The benchmark
    # button is transient (clicked=True only on the run that clicked it),
    # so persist the chosen source in session_state to survive reruns
    # triggered by selectbox/tab/download interactions.
    # ------------------------------------------------------------------
    if use_benchmark:
        if not BENCHMARK_PDF.exists():
            st.error(f"Benchmark PDF not found at `{BENCHMARK_PDF}`.")
            st.stop()
        st.session_state["_source"] = {
            "name": BENCHMARK_PDF.name,
            "stem": BENCHMARK_PDF.stem,
            "path": str(BENCHMARK_PDF),
            "key": f"benchmark:{BENCHMARK_PDF.name}:{BENCHMARK_PDF.stat().st_size}",
        }
    elif uploaded is not None:
        upload_key = f"{uploaded.name}:{uploaded.size}"
        if st.session_state.get("_upload_key") != upload_key:
            # Persist the in-memory upload to a temp file (the pipeline
            # expects a path, not a buffer).
            tmp_path = Path(tempfile.gettempdir()) / f"acs_upload_{uploaded.name}"
            tmp_path.write_bytes(uploaded.getvalue())
            st.session_state["_upload_key"] = upload_key
            st.session_state["_upload_path"] = str(tmp_path)
        st.session_state["_source"] = {
            "name": uploaded.name,
            "stem": Path(uploaded.name).stem,
            "path": st.session_state.get("_upload_path"),
            "key": f"upload:{upload_key}",
        }

    source = st.session_state.get("_source")
    if source is None:
        st.info("👈 Upload a PDF (or load the benchmark) to get started.")
        st.stop()
    if source.get("path") is None:
        st.stop()

    source_name = source["name"]
    source_stem = source["stem"]
    source_path = source["path"]
    source_key = source["key"]

    # ------------------------------------------------------------------
    # Extract (cached per document, per browser session)
    # ------------------------------------------------------------------
    if st.session_state.get("_results_key") != source_key:
        try:
            with st.spinner("Extracting schedule data..."):
                start = time.perf_counter()
                regions = _extract(source_path)
                elapsed = time.perf_counter() - start
            simplified = simplify_for_presentation(regions)
            st.session_state["_regions"] = regions
            st.session_state["_simplified"] = simplified
            st.session_state["_elapsed"] = elapsed
            st.session_state["_error"] = None
        except Exception as exc:  # noqa: BLE001 — surface pipeline errors to the UI
            st.session_state["_regions"] = []
            st.session_state["_simplified"] = None
            st.session_state["_error"] = str(exc)
        st.session_state["_results_key"] = source_key

    if st.session_state.get("_error"):
        st.error(f"**Extraction failed** — {st.session_state['_error']}")
        st.info(
            "The file must be a valid AutoCAD-exported vector PDF (embedded text, "
            "not a scanned image). If the upload looks right, check the "
            "extraction logs below the error."
        )
        st.stop()

    regions = st.session_state.get("_regions") or []
    simplified = st.session_state.get("_simplified") or {"tables": []}

    if not regions:
        st.warning(
            "No schedule regions were detected in this PDF. "
            "It may not contain anchored schedule/notes titles the pipeline recognises."
        )
        st.stop()

    # ------------------------------------------------------------------
    # Summary header
    # ------------------------------------------------------------------
    n_notes = sum(1 for r in regions if _is_notes(r))
    n_tables = len(regions) - n_notes
    n_vector = sum(1 for r in regions if _strategy_of(r) == "vector")
    n_text = sum(1 for r in regions if _strategy_of(r) == "text_clustering")

    st.success(f"Extracted **{len(regions)}** region(s) from `{source_name}` in {st.session_state.get('_elapsed', 0):.2f}s")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Regions", len(regions))
    m2.metric("Schedule tables", n_tables)
    m3.metric("Notes panels", n_notes)
    m4.metric("Vector-derived", n_vector)
    m5.metric("Text-clustered", n_text)

    # ------------------------------------------------------------------
    # Region selector + tabs
    # ------------------------------------------------------------------
    st.divider()
    labels = [f"{i + 1}. {_region_name(r)}" for i, r in enumerate(regions)]
    selected = st.selectbox("Region", labels, key="region_selector")
    idx = labels.index(selected)
    region = regions[idx]
    simplified_entry = simplified["tables"][idx] if idx < len(simplified["tables"]) else {}

    st.caption(f"Source file: `{source_name}`")
    _render_strategy_badge(region)
    _render_region_diagnostics(region)

    tab_review, tab_canonical = st.tabs(["Review view", "Canonical JSON"])
    with tab_review:
        _render_review_tab(region, simplified_entry, source_stem, idx)
    with tab_canonical:
        _render_canonical_tab(region, source_stem, idx)

    # ------------------------------------------------------------------
    # Full-document downloads (also mirrored in the sidebar when ready)
    # ------------------------------------------------------------------
    full_canonical = _to_json(regions)
    full_simplified = _to_json(simplified)

    with st.sidebar:
        if st.session_state.get("_regions"):
            st.download_button(
                "Canonical JSON (full)",
                data=full_canonical,
                file_name=f"{source_stem}_canonical.json",
                mime="application/json",
                key="dl_full_canonical",
                width="stretch",
            )
            st.download_button(
                "Presentation JSON (full)",
                data=full_simplified,
                file_name=f"{source_stem}_simplified.json",
                mime="application/json",
                key="dl_full_simplified",
                width="stretch",
            )

    with st.expander("Full canonical JSON — all regions"):
        st.json(regions)
    with st.expander("Full presentation JSON — all regions"):
        st.json(simplified)

    st.caption("Demo/review tool — not the planned Phase 5 production UI.")


if __name__ == "__main__":
    main()
