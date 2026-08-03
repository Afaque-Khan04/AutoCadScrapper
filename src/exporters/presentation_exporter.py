"""
Flattens the full canonical extraction JSON (engineering/audit format --
per-cell bbox, confidence, normalized_value, merged_header_cells, header
canonical-field metadata, etc.) into a simplified presentation view: table
name -> rows as flat {header: value} dicts, or for general_notes, a flat
{label: value} dict.

Keep the full JSON as the source of truth for debugging/validation --
generate this view only when output needs to go in front of a
non-technical reviewer. Nothing here is destructive to the original file;
this only reads it and produces a new, separate structure.
"""

from __future__ import annotations
import json
from pathlib import Path


def _humanize(field_name: str) -> str:
    """Converts a snake_case canonical field name to Title Case for display."""
    return " ".join(word.capitalize() for word in field_name.replace("_", " ").split())


def _flatten_general_notes(table: dict) -> dict:
    """
    Flattens the general_notes table into section headings, ordered to
    match the visual top-to-bottom hierarchy in the source drawing
    (GENERAL NOTES items, then COVER, then the standalone dimensions
    note, then LEGENDS) rather than whatever order the underlying data
    happens to carry:

    - Top-level items (no sub-section) go under "notes" -- reserved as
      the first key so it always renders first, matching "GENERAL
      NOTES:" being the top heading in the drawing.
    - Any nested section (e.g. "cover": {"column": "40mm"}) becomes its
      OWN heading, appended in the order it appears in the source data
      -- generalizes to any future sectioned notes, not just "cover".
    - "additional_notes" (standalone lines with no paired value, e.g.
      "ALL DIMENSIONS ARE IN MM") comes next, matching where it sits
      between COVER and LEGENDS in the drawing.
    - "legends" comes last, matching its position as the final
      sub-section in the drawing.
    - Anything that couldn't be captured as text (e.g. the Erection
      Mark, a drawn symbol with no OCR-able text) keeps a null value in
      its section, plus is called out explicitly in "flags".
    """
    result: dict = {"notes": {}}
    unresolved: list[str] = []
    nested_sections: dict = {}

    for key, value in table.get("general_notes", {}).items():
        if isinstance(value, dict):  # a nested section -> its own heading, in source order
            nested_sections[_humanize(key)] = {_humanize(k): v for k, v in value.items()}
        else:
            result["notes"][_humanize(key)] = value

    if not result["notes"]:
        del result["notes"]
    result.update(nested_sections)

    metadata = table.get("metadata", [])
    if metadata:
        result["additional_notes"] = [note.capitalize() for note in metadata]

    legends: dict[str, str | None] = {}
    for key, value in table.get("legends", {}).items():
        legends[_humanize(key)] = value or None
        if not value:
            unresolved.append(f"{_humanize(key)} (symbol/icon in source drawing -- not text-extractable)")
    if legends:
        result["legends"] = legends

    if unresolved:
        result["flags"] = unresolved
    return result


def _flatten_schedule_table(table: dict) -> list[dict]:
    """Flattens a headers+rows schedule table into a list of {raw_header: raw_text} row dicts."""
    header_by_index = {h["col_index"]: h["raw_header"] for h in table.get("headers", [])}
    flat_rows = []
    for row in table.get("rows", []):
        flat_rows.append({
            header_by_index.get(cell["col_index"], f"col_{cell['col_index']}"): cell["raw_text"]
            for cell in row.get("cells", [])
        })
    return flat_rows


def simplify_for_presentation(tables: list[dict]) -> dict:
    """
    Main entry point: takes the full canonical extraction output (a list
    of table dicts, as produced by table_builder.extract_all_tables or
    extract_all_regions) and returns a simplified structure for a non-technical
    reviewer -- table name, and either a flat notes dict or a list of flat
    row dicts, with all bbox/confidence/schema scaffolding stripped out.
    """
    simplified = {"tables": []}

    for table in tables:
        # de-dupe repeated title text (e.g. "GENERAL NOTES:\nGENERAL NOTES:")
        # by taking only the first line and dropping a trailing colon
        raw_title = table.get("title_raw", "")
        name = raw_title.split("\n")[0].strip().rstrip(":") if raw_title else table.get("table_type", "Table")
        entry = {
            "name": name,
            "type": table.get("table_type", ""),
        }
        is_notes = (
            table.get("table_type") == "general_notes"
            or table.get("region_type") in ("general_notes", "legend", "specifications")
            or "general_notes" in table
        )
        if is_notes:
            entry.update(_flatten_general_notes(table))
        else:
            entry["rows"] = _flatten_schedule_table(table)
        simplified["tables"].append(entry)

    return simplified


def export_presentation_json(tables: list[dict], output_path: str | Path | None = None) -> str:
    """Simplifies canonical extraction tables and optionally writes JSON to file."""
    simplified = simplify_for_presentation(tables)
    json_str = json.dumps(simplified, indent=2, ensure_ascii=False)
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json_str, encoding="utf-8")
    return json_str


def export_to_output_dir(
    pdf_path: str | Path,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    """
    End-to-end: extracts all regions from a PDF, then writes both the
    full canonical JSON and the simplified presentation JSON into
    `output_dir` (defaults to ``<project_root>/output/``).

    File names are derived from the PDF stem:
      - ``<stem>_canonical.json``  — full engineering/audit JSON
      - ``<stem>_simplified.json`` — reviewer-friendly presentation JSON

    Returns a dict with keys ``"canonical"`` and ``"simplified"`` mapping
    to the written file paths.
    """
    # pyrefly: ignore [missing-import]
    from ..tables.table_builder import extract_all_regions

    pdf_path = Path(pdf_path)
    if output_dir is None:
        # Default: <project_root>/output/
        output_dir = Path(__file__).resolve().parent.parent.parent / "output"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = pdf_path.stem

    # 1. Extract canonical data
    canonical_tables = extract_all_regions(str(pdf_path))

    # 2. Write canonical JSON
    canonical_path = output_dir / f"{stem}_canonical.json"
    canonical_json = json.dumps(canonical_tables, indent=2, ensure_ascii=False)
    canonical_path.write_text(canonical_json, encoding="utf-8")

    # 3. Write simplified presentation JSON
    simplified_path = output_dir / f"{stem}_simplified.json"
    export_presentation_json(canonical_tables, output_path=simplified_path)

    return {"canonical": canonical_path, "simplified": simplified_path}


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.exporters.presentation_exporter <path_to_pdf>")
        sys.exit(1)

    target = Path(sys.argv[1])

    if target.suffix.lower() == ".pdf":
        paths = export_to_output_dir(target)
        print(f"Canonical JSON:   {paths['canonical']}")
        print(f"Simplified JSON:  {paths['simplified']}")
    else:
        # Treat as pre-existing canonical JSON — just print simplified
        with open(target, encoding="utf-8") as f:
            canonical_tables = json.load(f)
        print(export_presentation_json(canonical_tables))
