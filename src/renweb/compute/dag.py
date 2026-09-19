"""Run the statistics for every requested country-year."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pyarrow as pa

from renweb.compute.formulas import METHOD_VERSION, Frame, compute_one
from renweb.compute.optional import attach_optional


def compute(
    con: Any,
    countries: list[str] | None = None,
    years: list[int] | None = None,
) -> int:
    """Calculate results from the ``web`` view. Replaces rows for this method version."""
    where = ["value_tj IS NOT NULL", "unit_status <> 'suspect'"]
    params: list[object] = []
    if countries:
        placeholders = ", ".join("?" for _ in countries)
        where.append(f"country IN ({placeholders})")
        params.extend(countries)
    if years:
        placeholders = ", ".join("?" for _ in years)
        where.append(f"year IN ({placeholders})")
        params.extend(years)
    sql = (
        "SELECT country, year, flow, product, value_tj FROM web WHERE "
        + " AND ".join(where)
    )
    fetched = con.execute(sql, params).fetchall()
    grouped: dict[tuple[str, int], dict[tuple[str, str], float]] = defaultdict(dict)
    for country, year, flow, product, value in fetched:
        grouped[(country, int(year))][(flow, product)] = float(value)
    if not grouped:
        return 0

    delete_where = ["method_version = ?"]
    delete_params: list[object] = [METHOD_VERSION]
    if countries:
        placeholders = ", ".join("?" for _ in countries)
        delete_where.append(f"country IN ({placeholders})")
        delete_params.extend(countries)
    if years:
        placeholders = ", ".join("?" for _ in years)
        delete_where.append(f"year IN ({placeholders})")
        delete_params.extend(years)
    con.execute(
        "DELETE FROM results WHERE " + " AND ".join(delete_where),
        delete_params,
    )

    countries_out: list[str] = []
    years_out: list[int] = []
    variables: list[str] = []
    values: list[float] = []
    units: list[str] = []
    versions: list[str] = []
    for (country, year), pairs in sorted(grouped.items()):
        calculated = compute_one(Frame.from_pairs(pairs), country, year)
        for variable, (value, unit) in calculated.items():
            countries_out.append(country)
            years_out.append(year)
            variables.append(variable)
            values.append(value)
            units.append(unit)
            versions.append(METHOD_VERSION)
    table = pa.table(
        {
            "country": countries_out,
            "year": years_out,
            "variable": variables,
            "value": values,
            "unit": units,
            "method_version": versions,
        }
    )
    con.register("_results_batch", table)
    con.execute("INSERT INTO results SELECT * FROM _results_batch")
    con.unregister("_results_batch")
    attach_optional(con, countries, years)
    return len(grouped)
