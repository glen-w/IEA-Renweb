"""Load World Bank population, GDP, and income into the warehouse."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from renweb.compute.optional import attach_optional
from renweb.ingest.http import request_json
from renweb.ingest.pipeline import IngestError

WB_API = "https://api.worldbank.org/v2"
INDICATORS = (
    ("SP.POP.TOTL", "1"),
    ("NY.GDP.MKTP.CD", "USD"),
    ("NY.GDP.MKTP.PP.KD", "USD"),
)

Fetch = Callable[..., Any]


@dataclass(frozen=True)
class WorldBankReport:
    indicators: int
    income_rows: int
    attached: int


def ingest_worldbank(
    con: Any,
    *,
    start_year: int | None = None,
    end_year: int | None = None,
    fetch: Fetch | None = None,
) -> WorldBankReport:
    """Replace ``wb_indicators`` and ``wb_income``, then attach result rows."""
    getter = fetch or _default_fetch
    rows = _indicators(getter, start_year, end_year)
    if not rows:
        raise IngestError("World Bank API returned no indicator rows.")
    income = _income(getter)
    con.execute("DELETE FROM wb_indicators")
    con.execute("DELETE FROM wb_income")
    con.executemany(
        "INSERT INTO wb_indicators VALUES (?, ?, ?, ?, ?, current_timestamp)",
        rows,
    )
    if income:
        con.executemany(
            "INSERT INTO wb_income VALUES (?, ?, ?, current_timestamp)",
            income,
        )
    attached = attach_optional(con)
    return WorldBankReport(len(rows), len(income), attached)


def _default_fetch(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    return request_json(
        "worldbank",
        "World Bank",
        method,
        url,
        params=params,
        json_body=json_body,
    )


def _indicators(
    fetch: Fetch,
    start_year: int | None,
    end_year: int | None,
) -> list[tuple[str, int, str, float, str]]:
    rows: list[tuple[str, int, str, float, str]] = []
    for code, unit in INDICATORS:
        page = 1
        pages = 1
        while page <= pages:
            payload = fetch(
                "GET",
                f"{WB_API}/country/all/indicator/{code}",
                params=_page_params(page, start_year, end_year),
            )
            header, records = _pages(payload)
            pages = int(header.get("pages") or 1)
            for record in records:
                country = str(record.get("countryiso3code") or "").strip().upper()
                date = record.get("date")
                value = record.get("value")
                if not country or date is None or value is None:
                    continue
                rows.append((country, int(date), code, float(value), unit))
            page += 1
    return rows


def _income(fetch: Fetch) -> list[tuple[str, str, str]]:
    payload = fetch(
        "GET",
        f"{WB_API}/country",
        params={"format": "json", "per_page": 400},
    )
    _, records = _pages(payload)
    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for record in records:
        if str(record.get("region", {}).get("id") or "") == "NA":
            continue
        country = str(record.get("id") or "").strip().upper()
        level = record.get("incomeLevel") or {}
        level_id = str(level.get("id") or "").strip()
        label = str(level.get("value") or "").strip()
        if len(country) != 3 or not level_id or country in seen:
            continue
        seen.add(country)
        rows.append((country, level_id, label))
    return rows


def _page_params(
    page: int, start_year: int | None, end_year: int | None
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "format": "json",
        "per_page": 20000,
        "page": page,
    }
    if start_year is not None or end_year is not None:
        low = start_year if start_year is not None else 1960
        high = end_year if end_year is not None else datetime.now().year
        params["date"] = f"{low}:{high}"
    return params


def _pages(payload: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(payload, list) or len(payload) < 2:
        raise IngestError("Unexpected World Bank API response.")
    header = payload[0] if isinstance(payload[0], dict) else {}
    records = payload[1] if isinstance(payload[1], list) else []
    return header, records
