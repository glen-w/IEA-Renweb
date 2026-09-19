"""Load IRENASTAT electricity capacity into the warehouse."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from renweb.compute.optional import attach_optional
from renweb.ingest.http import request_json
from renweb.ingest.pipeline import IngestError

IRENA_FOLDER = (
    "https://pxweb.irena.org/api/v1/en/IRENASTAT/Power Capacity and Generation"
)

Fetch = Callable[..., Any]


@dataclass(frozen=True)
class IrenaReport:
    rows: int
    attached: int
    table: str | None


def ingest_irena(
    con: Any,
    path: str | Path | None = None,
    *,
    fetch: Fetch | None = None,
) -> IrenaReport:
    """Replace ``capacity``, then attach result rows for matching IEA years."""
    if path is not None:
        rows = _from_csv(con, Path(path))
        table = None
    else:
        getter = fetch or _default_fetch
        table, rows = _from_api(getter)
    if not rows:
        raise IngestError("No IRENA capacity rows to store.")
    con.execute("DELETE FROM capacity")
    con.executemany("INSERT INTO capacity VALUES (?, ?, ?, ?, ?)", rows)
    attached = attach_optional(con)
    return IrenaReport(len(rows), attached, table)


def _default_fetch(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    return request_json(
        "irena",
        "IRENA",
        method,
        url,
        params=params,
        json_body=json_body,
    )


def _from_csv(con: Any, path: Path) -> list[tuple[str, int, str, str, float]]:
    target = path.expanduser()
    if not target.is_file():
        raise IngestError(f"No such file: {target}")
    escaped = str(target.resolve()).replace("'", "''")
    try:
        fetched = con.execute(f"""
            SELECT
                upper(trim(CAST(country AS VARCHAR))),
                CAST(year AS INTEGER),
                CAST(technology AS VARCHAR),
                CAST(grid AS VARCHAR),
                CAST(capacity_mw AS DOUBLE)
            FROM read_csv_auto('{escaped}', HEADER=TRUE)
            WHERE capacity_mw IS NOT NULL
            """).fetchall()
    except Exception as exc:
        raise IngestError(f"Could not read capacity CSV: {exc}") from exc
    rows: list[tuple[str, int, str, str, float]] = []
    for country, year, technology, grid, value in fetched:
        if not country or year is None or not technology or not grid:
            continue
        rows.append((str(country), int(year), str(technology), str(grid), float(value)))
    return rows


def _from_api(fetch: Fetch) -> tuple[str, list[tuple[str, int, str, str, float]]]:
    listing = fetch("GET", IRENA_FOLDER)
    table_id = discover_capacity_table(listing)
    meta = fetch("GET", f"{IRENA_FOLDER}/{quote(table_id, safe='')}")
    years = _year_codes(meta)
    rows: list[tuple[str, int, str, str, float]] = []
    for code, _year in years:
        payload = fetch(
            "POST",
            f"{IRENA_FOLDER}/{quote(table_id, safe='')}",
            json_body={
                "query": [
                    {
                        "code": "Country/area",
                        "selection": {"filter": "all", "values": ["*"]},
                    },
                    {
                        "code": "Technology",
                        "selection": {"filter": "all", "values": ["*"]},
                    },
                    {
                        "code": "Grid connection",
                        "selection": {"filter": "all", "values": ["*"]},
                    },
                    {
                        "code": "Year",
                        "selection": {"filter": "item", "values": [code]},
                    },
                ],
                "response": {"format": "json-stat2"},
            },
        )
        rows.extend(decode_jsonstat2(payload))
    return table_id, rows


def discover_capacity_table(listing: Any) -> str:
    if not isinstance(listing, list):
        raise IngestError("Unexpected IRENASTAT folder listing.")
    matches = [
        str(item.get("id"))
        for item in listing
        if isinstance(item, dict)
        and str(item.get("id") or "").startswith("Country_ELECCAP")
    ]
    if not matches:
        raise IngestError("No country electricity-capacity table in IRENASTAT.")
    return sorted(matches)[-1]


def decode_jsonstat2(
    payload: dict[str, Any],
) -> list[tuple[str, int, str, str, float]]:
    ids = payload.get("id")
    sizes = payload.get("size")
    if not ids or not sizes or len(ids) != len(sizes):
        raise IngestError("Unexpected IRENA json-stat2 payload.")
    raw_values = payload.get("value", [])
    axes: list[list[str]] = []
    for name, size in zip(ids, sizes, strict=True):
        category = payload["dimension"][name]["category"]
        index = category["index"]
        labels = category.get("label") or {}
        slot = [""] * int(size)
        for code, position in index.items():
            pos = int(position)
            if name == "Country/area":
                slot[pos] = str(code).strip().upper()
            else:
                slot[pos] = str(labels.get(code, code))
        axes.append(slot)
    count = 1
    for size in sizes:
        count *= int(size)
    rows: list[tuple[str, int, str, str, float]] = []
    for i in range(count):
        value = _stat_value(raw_values, i)
        if value is None:
            continue
        remaining = i
        coords: list[int] = []
        for size in reversed(sizes):
            coords.append(remaining % int(size))
            remaining //= int(size)
        coords.reverse()
        fields = {name: axes[dim][coords[dim]] for dim, name in enumerate(ids)}
        country = fields.get("Country/area") or ""
        technology = fields.get("Technology") or ""
        grid = fields.get("Grid connection") or ""
        year_text = fields.get("Year") or ""
        if not country or not technology or not grid or not year_text:
            continue
        rows.append((country, int(year_text), technology, grid, value))
    return rows


def _year_codes(meta: dict[str, Any]) -> list[tuple[str, int]]:
    for variable in meta.get("variables") or []:
        if variable.get("code") != "Year":
            continue
        values = variable.get("values") or []
        texts = variable.get("valueTexts") or []
        return list(zip((str(v) for v in values), (int(t) for t in texts), strict=True))
    raise IngestError("IRENA capacity table has no Year dimension.")


def _stat_value(values: Any, index: int) -> float | None:
    if values is None:
        return None
    if isinstance(values, dict):
        item = values.get(str(index), values.get(index))
    else:
        if index >= len(values):
            return None
        item = values[index]
    if item is None:
        return None
    try:
        return float(item)
    except (TypeError, ValueError):
        return None
