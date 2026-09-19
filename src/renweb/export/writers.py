"""Parquet, CSV, and xlsx writers."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class ExportError(RuntimeError):
    """The requested format cannot be written."""


def export_results(con: Any, dest: Path, formats: list[str]) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    count = con.execute("SELECT count(*) FROM results").fetchone()[0]
    if count == 0:
        raise ExportError("No results to export. Run compute first.")
    written: list[Path] = []
    query = "SELECT * FROM results ORDER BY country, year, variable"
    for fmt in formats:
        if fmt == "parquet":
            path = dest / "results.parquet"
            con.execute(f"COPY ({query}) TO '{_sql_path(path)}' (FORMAT PARQUET)")
            written.append(path)
        elif fmt == "csv":
            path = dest / "results.csv"
            con.execute(f"COPY ({query}) TO '{_sql_path(path)}' (FORMAT CSV, HEADER)")
            written.append(path)
        elif fmt == "xlsx":
            written.append(_xlsx(con, dest / "results.xlsx", query))
        else:
            raise ExportError(f"Unknown format {fmt!r}. Use parquet, csv, or xlsx.")
    return written


def _sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def _xlsx(con: Any, path: Path, query: str) -> Path:
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        raise ExportError(
            "xlsx export needs the xlsx extra: pip install 'renweb[xlsx]'"
        ) from exc
    rows = con.execute(query).fetchall()
    if len(rows) > 1_048_575:
        raise ExportError(
            f"{len(rows)} result rows do not fit in a worksheet. Use parquet or csv."
        )
    book = Workbook(write_only=True)
    sheet = book.create_sheet("results")
    sheet.append(["country", "year", "variable", "value", "unit", "method_version"])
    for row in rows:
        sheet.append(list(row))
    book.save(path)
    return path
