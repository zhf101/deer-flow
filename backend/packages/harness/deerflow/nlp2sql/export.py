from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from deerflow.nlp2sql.types import QueryExecutionResult

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_filename(name: str) -> str:
    sanitized = _SAFE_FILENAME_RE.sub("-", name).strip("-")
    return sanitized or "query-result"


def _default_filename(result: QueryExecutionResult, format_name: str) -> str:
    base = _sanitize_filename(result.data_source_id or "query-result")
    return f"{base}.{format_name}"


def _render_markdown_table(result: QueryExecutionResult) -> str:
    columns = result.columns
    header = "| " + " | ".join(columns) + " |"
    divider = "|" + "|".join("---" for _ in columns) + "|"
    rows = [
        "| " + " | ".join(str(row.get(column, "")) for column in columns) + " |"
        for row in result.rows
    ]
    return "\n".join([header, divider, *rows])


def export_last_result(
    outputs_dir: Path,
    result: QueryExecutionResult,
    format: str,
    filename: str | None = None,
) -> Path:
    format_name = format.lower().strip()
    if format_name not in {"csv", "json", "md", "markdown"}:
        raise ValueError("Format must be one of: csv, json, md, markdown")

    extension = "md" if format_name == "markdown" else format_name
    resolved_name = _sanitize_filename(filename) if filename else _default_filename(result, extension)
    if not resolved_name.endswith(f".{extension}"):
        resolved_name = f"{resolved_name}.{extension}"

    outputs_dir.mkdir(parents=True, exist_ok=True)
    output_path = outputs_dir / resolved_name

    if extension == "csv":
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=result.columns)
            writer.writeheader()
            writer.writerows(result.rows)
    elif extension == "json":
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result.model_dump(mode="json"), f, indent=2, ensure_ascii=False, default=str)
    else:
        output_path.write_text(_render_markdown_table(result), encoding="utf-8")

    return output_path
