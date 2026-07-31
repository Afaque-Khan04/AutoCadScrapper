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
    Flattens the general_notes table's nested structure (general_notes /
    cover / legends / metadata) into one flat label->value dict, plus a
    separate "flags" list for anything that couldn't be captured as text
    (e.g. the Erection Mark, which is a drawn symbol with no OCR-able
    text -- shown as a flag instead of a silent blank value).
    """
    flat: dict[str, str | None] = {}
    unresolved: list[str] = []

    notes = table.get("general_notes", {})
    for key, value in notes.items():
        if isinstance(value, dict):  # one level of nesting, e.g. "cover": {"column": "40mm"}
            for sub_key, sub_value in value.items():
                flat[f"{_humanize(key)} - {_humanize(sub_key)}"] = sub_value
        else:
            flat[_humanize(key)] = value

    for key, value in table.get("legends", {}).items():
        if value:
            flat[_humanize(key)] = value
        else:
            unresolved.append(f"{_humanize(key)} (symbol/icon in source drawing -- not text-extractable)")

    for note in table.get("metadata", []):
        flat[note.capitalize()] = None  # standalone note, no associated value

    result = {"notes": flat}
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
        Path(output_path).write_text(json_str, encoding="utf-8")
    return json_str


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.exporters.presentation_exporter <path_to_pdf_or_canonical_json>")
        sys.exit(1)

    target = sys.argv[1]
    if target == "-":
        canonical_tables = json.load(sys.stdin)
    elif target.lower().endswith(".pdf"):
        from src.tables.table_builder import extract_all_regions
        canonical_tables = extract_all_regions(target)
    else:
        with open(target, encoding="utf-8") as f:
            canonical_tables = json.load(f)

    print(export_presentation_json(canonical_tables))

