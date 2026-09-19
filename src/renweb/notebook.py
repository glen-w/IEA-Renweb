"""Queries, controls, and charts for the optional marimo notebook.

The notebook in ``notebooks/quicklook.py`` is a quick look at the warehouse, not
a second calculation path. Everything here reads; nothing writes. The helpers
take ``mo`` (marimo) and ``px`` (plotly.express) as arguments so this module
imports only duckdb and pandas and stays testable without a browser.

The notebook file is not called ``renweb.py``: marimo puts the notebook
directory on ``sys.path``, and a file of that name would shadow this package.

Widgets must be bound to their own notebook globals to be reactive; marimo
does not look inside a container such as :class:`Controls`, so the notebook
unpacks it.

Several helpers are adapted from the data_dumps project (same author, MIT):
the read-only connect guard, ``has_table``, ``normalize_pct_of_max``, the
year-slider guard for single-year warehouses, and the overlay / choropleth
chart builders.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from renweb.validate.checks import Finding
from renweb.warehouse import warehouse_path

MAX_COMPARE = 6

ECONOMY_SHARES: tuple[str, ...] = (
    "economy_share_renewable",
    "economy_share_fossil",
    "economy_share_nuclear",
    "economy_share_modern_renewables",
    "economy_share_traditional_biomass",
)
SECTOR_SHARES: tuple[str, ...] = (
    "power_share_renewable",
    "buildings_renewable_share",
    "industry_renewable_share",
    "transport_renewable_share",
    "agriculture_renewable_share",
    "heat_renewable_share",
)
TFEC_STACK: tuple[str, ...] = (
    "economy_tfec_fossil_tj",
    "economy_tfec_nuclear_tj",
    "economy_tfec_renewable_tj",
)
DEFAULT_VARIABLE = "economy_share_renewable"
# Compare defaults: large economies when present, else the first codes. On a
# full extract the alphabetical start is AFRICA, AGO, ALB, which is not useful.
PREFERRED_COMPARE: tuple[str, ...] = ("CHN", "USA", "IND", "DEU", "FRA", "BRA")
DEFAULT_COMPARE_COUNT = 3

OPTIONAL_TABLES: tuple[str, ...] = ("wb_indicators", "wb_income", "capacity")

SERIES_COLS = ["year", "variable", "value", "unit"]
COMPARE_COLS = ["year", "country", "value", "unit"]
MAP_COLS = ["country", "value"]
FINDING_COLS = ["severity", "check", "country", "year", "variable", "message"]

# ``results.unit`` is "1" for a share. Axis labels read better spelled out.
UNIT_LABELS = {"1": "share (fraction)", "TJ": "TJ", "MW": "MW"}
# ``mo.ui.table`` formats integers with thousands separators; years should not be.
TABLE_FORMATS = {"year": "{:d}"}


def unit_label(unit: Any) -> str:
    text = "" if unit is None else str(unit)
    return UNIT_LABELS.get(text, text)


# --------------------------------------------------------------------------- #
# Connection
# --------------------------------------------------------------------------- #


def connect_read_only(path: Path | None = None) -> Any:
    """Open the warehouse read-only.

    ``renweb.warehouse.connect`` runs ``CREATE`` statements, which a read-only
    connection rejects, so the notebook opens the file directly. The ``web``
    view is already stored in the file.
    """
    db = path or warehouse_path()
    if not db.exists():
        raise FileNotFoundError(
            f"No warehouse at {db}. Run `uv run renweb ingest /path/to/extract` "
            "and `uv run renweb compute`, then reopen this notebook."
        )
    return duckdb.connect(str(db), read_only=True)


def has_table(con: Any, name: str) -> bool:
    row = con.execute(
        """
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = ?
        """,
        [name],
    ).fetchone()
    return row is not None and row[0] > 0


# --------------------------------------------------------------------------- #
# Queries
# --------------------------------------------------------------------------- #


def overview(con: Any) -> dict[str, Any]:
    """What is in the warehouse: sources, balances span, unit check, results."""
    sources = con.execute("""
        SELECT filename, format, row_count, null_count, unmapped_count, ingested_at
        FROM source ORDER BY ingested_at
        """).df()
    web_row = con.execute(
        "SELECT count(DISTINCT country), min(year), max(year), count(*) FROM web"
    ).fetchone()
    unit_status = con.execute(
        "SELECT unit_status, count(*) AS rows FROM web GROUP BY 1 ORDER BY 2 DESC"
    ).df()
    results_row = con.execute(
        "SELECT count(*), count(DISTINCT country), min(year), max(year) FROM results"
    ).fetchone()
    versions = [
        str(row[0])
        for row in con.execute(
            "SELECT DISTINCT method_version FROM results ORDER BY 1"
        ).fetchall()
    ]
    optional: dict[str, int] = {}
    for table in OPTIONAL_TABLES:
        if has_table(con, table):
            count = con.execute(f"SELECT count(*) FROM {table}").fetchone()
            optional[table] = int(count[0]) if count else 0
        else:
            optional[table] = 0
    return {
        "sources": sources,
        "web_countries": int(web_row[0]) if web_row else 0,
        "web_min_year": _int_or_none(web_row[1] if web_row else None),
        "web_max_year": _int_or_none(web_row[2] if web_row else None),
        "web_rows": int(web_row[3]) if web_row else 0,
        "unit_status": unit_status,
        "results_rows": int(results_row[0]) if results_row else 0,
        "results_countries": int(results_row[1]) if results_row else 0,
        "results_min_year": _int_or_none(results_row[2] if results_row else None),
        "results_max_year": _int_or_none(results_row[3] if results_row else None),
        "method_versions": versions,
        "optional": optional,
    }


def countries(con: Any) -> list[str]:
    rows = con.execute("SELECT DISTINCT country FROM results ORDER BY 1").fetchall()
    return [str(row[0]) for row in rows]


def variables(con: Any) -> list[str]:
    rows = con.execute("SELECT DISTINCT variable FROM results ORDER BY 1").fetchall()
    return [str(row[0]) for row in rows]


def year_bounds(con: Any) -> tuple[int, int] | None:
    row = con.execute("SELECT min(year), max(year) FROM results").fetchone()
    if row is None or row[0] is None or row[1] is None:
        return None
    return int(row[0]), int(row[1])


def country_series(
    con: Any,
    country: str,
    year_start: int | None,
    year_end: int | None,
    variables: tuple[str, ...] | list[str],
) -> pd.DataFrame:
    """Long frame ``year, variable, value, unit`` for one country."""
    if not variables:
        return pd.DataFrame(columns=SERIES_COLS)
    where = ["country = ?"]
    params: list[Any] = [country]
    _append_years(where, params, year_start, year_end)
    placeholders = ", ".join("?" for _ in variables)
    where.append(f"variable IN ({placeholders})")
    params.extend(variables)
    frame = con.execute(
        "SELECT year, variable, value, unit FROM results WHERE "
        + " AND ".join(where)
        + " ORDER BY year, variable",
        params,
    ).df()
    return frame if not frame.empty else pd.DataFrame(columns=SERIES_COLS)


def compare_series(
    con: Any,
    countries: list[str],
    variable: str,
    year_start: int | None,
    year_end: int | None,
) -> pd.DataFrame:
    """Long frame ``year, country, value, unit`` for one variable."""
    picked = list(countries)[:MAX_COMPARE]
    if not picked or not variable:
        return pd.DataFrame(columns=COMPARE_COLS)
    where = ["variable = ?"]
    params: list[Any] = [variable]
    _append_years(where, params, year_start, year_end)
    placeholders = ", ".join("?" for _ in picked)
    where.append(f"country IN ({placeholders})")
    params.extend(picked)
    frame = con.execute(
        "SELECT year, country, value, unit FROM results WHERE "
        + " AND ".join(where)
        + " ORDER BY country, year",
        params,
    ).df()
    return frame if not frame.empty else pd.DataFrame(columns=COMPARE_COLS)


def map_frame(con: Any, variable: str, year: int) -> pd.DataFrame:
    """``country, value`` for one variable in one year.

    Aggregates such as ``WLD`` are not ISO-3 codes; plotly leaves them off
    the map without complaint.
    """
    frame = con.execute(
        """
        SELECT country, value FROM results
        WHERE variable = ? AND year = ? AND value IS NOT NULL
        ORDER BY country
        """,
        [variable, int(year)],
    ).df()
    return frame if not frame.empty else pd.DataFrame(columns=MAP_COLS)


def normalize_pct_of_max(
    df: pd.DataFrame, *, key: str = "country", value_col: str = "value"
) -> pd.DataFrame:
    """Add ``pct_of_max`` (0-100) per ``key``. A zero maximum gives zeros."""
    if df.empty:
        out = df.copy()
        if "pct_of_max" not in out.columns:
            out["pct_of_max"] = pd.Series(dtype=float)
        return out
    out = df.copy()
    out[value_col] = pd.to_numeric(out[value_col], errors="coerce").fillna(0.0)
    maxima = out.groupby(key)[value_col].transform("max")
    out["pct_of_max"] = 0.0
    nonzero = maxima > 0
    out.loc[nonzero, "pct_of_max"] = (
        out.loc[nonzero, value_col] / maxima[nonzero] * 100.0
    )
    return out.reset_index(drop=True)


def latest_values(df: pd.DataFrame, *, key: str = "country") -> pd.DataFrame:
    """One row per ``key``: the latest year present."""
    if df.empty or "year" not in df.columns:
        return df.copy()
    idx = df.groupby(key)["year"].idxmax()
    return df.loc[idx].sort_values(key).reset_index(drop=True)


def findings_frame(findings: list[Finding]) -> pd.DataFrame:
    rows = [
        {
            "severity": item.severity,
            "check": item.check,
            "country": item.country or "",
            "year": "" if item.year is None else str(item.year),
            "variable": item.variable or "",
            "message": item.message,
        }
        for item in findings
    ]
    return pd.DataFrame(rows, columns=FINDING_COLS)


def _append_years(
    where: list[str],
    params: list[Any],
    year_start: int | None,
    year_end: int | None,
) -> None:
    if year_start is not None:
        where.append("year >= ?")
        params.append(int(year_start))
    if year_end is not None:
        where.append("year <= ?")
        params.append(int(year_end))


def _int_or_none(value: Any) -> int | None:
    return None if value is None else int(value)


# --------------------------------------------------------------------------- #
# Controls
# --------------------------------------------------------------------------- #


@dataclass
class Controls:
    country: Any
    compare_countries: Any
    variable: Any
    pct_of_max: Any
    year_start: Any
    year_end: Any
    map_variable: Any
    map_year: Any


def default_compare_countries(
    countries: list[str], *, count: int = DEFAULT_COMPARE_COUNT
) -> list[str]:
    """Preferred large economies that exist, topped up from the list order."""
    present = set(countries)
    picked = [c for c in PREFERRED_COMPARE if c in present][:count]
    if len(picked) < count:
        for code in countries:
            if code == "WLD" or code in picked:
                continue
            picked.append(code)
            if len(picked) == count:
                break
    return picked or countries[:count]


def make_controls(
    mo: Any,
    bounds: tuple[int, int],
    countries: list[str],
    variables: list[str],
) -> Controls:
    """Build the widgets. Read their ``.value`` in a later cell (marimo rule)."""
    ys, ye = bounds
    if ys > ye:
        ys, ye = ye, ys
    # Sliders need stop > start; collapse single-year warehouses safely.
    stop = ye if ye > ys else ys + 1

    default_country = (
        "WLD" if "WLD" in countries else (countries[0] if countries else None)
    )
    default_compare = default_compare_countries(countries)
    default_variable = (
        DEFAULT_VARIABLE
        if DEFAULT_VARIABLE in variables
        else (variables[0] if variables else None)
    )
    share_variables = [v for v in variables if "share" in v] or variables
    default_map = (
        DEFAULT_VARIABLE
        if DEFAULT_VARIABLE in share_variables
        else (share_variables[0] if share_variables else None)
    )

    ms_kwargs: dict[str, Any] = {
        "options": countries,
        "value": default_compare,
        "label": f"Countries (max {MAX_COMPARE})",
    }
    try:
        compare_countries = mo.ui.multiselect(**ms_kwargs, max_selections=MAX_COMPARE)
    except TypeError:
        compare_countries = mo.ui.multiselect(**ms_kwargs)

    return Controls(
        country=mo.ui.dropdown(
            options=countries, value=default_country, label="Country"
        ),
        compare_countries=compare_countries,
        variable=mo.ui.dropdown(
            options=variables, value=default_variable, label="Variable"
        ),
        pct_of_max=mo.ui.switch(value=False, label="% of each country's max"),
        # show_value would print "2,015"; the render cells caption the years.
        year_start=mo.ui.slider(start=ys, stop=stop, value=ys, label="From year"),
        year_end=mo.ui.slider(start=ys, stop=stop, value=ye, label="To year"),
        map_variable=mo.ui.dropdown(
            options=share_variables, value=default_map, label="Map variable"
        ),
        map_year=mo.ui.slider(start=ys, stop=stop, value=ye, label="Map year"),
    )


def clamp_years(
    year_start: int, year_end: int, bounds: tuple[int, int]
) -> tuple[int, int]:
    """Clamp slider values to the warehouse span (the stop may be inflated)."""
    lo, hi = bounds
    ys = min(max(int(year_start), lo), hi)
    ye = min(max(int(year_end), lo), hi)
    if ys > ye:
        ys, ye = ye, ys
    return ys, ye


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #


def empty_figure(px: Any, title: str) -> Any:
    return px.line(title=title)


def line_chart(
    px: Any,
    df: pd.DataFrame,
    *,
    x: str,
    y: str,
    color: str,
    title: str,
    y_title: str,
    empty_title: str | None = None,
) -> Any:
    if df.empty or not {x, y, color} <= set(df.columns):
        return empty_figure(px, empty_title or title)
    fig = px.line(df, x=x, y=y, color=color, title=title, markers=True)
    fig.update_layout(xaxis_title="Year", yaxis_title=y_title, legend_title_text="")
    return fig


def overlay_chart(
    px: Any,
    df: pd.DataFrame,
    *,
    title: str,
    empty_title: str | None = None,
) -> Any:
    """Countries overlaid at ``% of own max``; hover shows the raw value and unit."""
    if df.empty or "pct_of_max" not in df.columns:
        return empty_figure(px, empty_title or title)
    has_raw = {"value", "unit"} <= set(df.columns)
    fig = px.line(
        df,
        x="year",
        y="pct_of_max",
        color="country",
        title=title,
        markers=True,
        custom_data=["value", "unit"] if has_raw else None,
    )
    fig.update_layout(
        xaxis_title="Year",
        yaxis_title="% of country max",
        legend_title_text="",
        yaxis={"range": [0, 105]},
    )
    if has_raw:
        fig.update_traces(
            hovertemplate=(
                "%{fullData.name}<br>%{x}: %{y:.1f}% of max"
                "<br>raw=%{customdata[0]:.4g} %{customdata[1]}<extra></extra>"
            )
        )
    return fig


def stacked_area(
    px: Any,
    df: pd.DataFrame,
    *,
    title: str,
    empty_title: str | None = None,
) -> Any:
    """TFEC split by ``variable`` over ``year``. Values are terajoules."""
    if df.empty or not {"year", "variable", "value"} <= set(df.columns):
        return empty_figure(px, empty_title or title)
    fig = px.area(df, x="year", y="value", color="variable", title=title)
    fig.update_layout(xaxis_title="Year", yaxis_title="TJ", legend_title_text="")
    return fig


def choropleth(
    px: Any,
    df: pd.DataFrame,
    *,
    title: str,
    locations: str = "country",
    color: str = "value",
    empty_title: str | None = None,
    height: int = 460,
) -> Any:
    """World map keyed by ISO-3 code. Zero values are kept."""
    if df.empty or not {locations, color} <= set(df.columns):
        return px.choropleth(title=empty_title or title)
    plot = df.dropna(subset=[locations, color]).copy()
    if plot.empty:
        return px.choropleth(title=empty_title or title)
    fig = px.choropleth(
        plot,
        locations=locations,
        color=color,
        locationmode="ISO-3",
        title=title,
        height=height,
        color_continuous_scale="Greens",
    )
    fig.update_layout(
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
        geo={"showframe": False, "showcoastlines": True},
    )
    return fig
