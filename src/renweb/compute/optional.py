"""Join World Bank and IRENA source tables onto IEA result rows."""

from __future__ import annotations

from typing import Any

from renweb.compute.formulas import METHOD_VERSION

WB_RESULT_VARS = (
    "population",
    "gdp_current_usd",
    "gdp_ppp_constant",
    "economy_tfec_per_capita_tj",
    "economy_tfec_renewable_per_capita_tj",
    "economy_tfec_per_gdp_ppp",
)

CAPACITY_TECHS = (
    ("Total renewable energy", "capacity_renewable_mw"),
    ("Solar photovoltaic", "capacity_solar_pv_mw"),
    ("Wind energy", "capacity_wind_mw"),
    ("Renewable hydropower", "capacity_hydro_mw"),
    ("Bioenergy", "capacity_bioenergy_mw"),
    ("Geothermal energy", "capacity_geothermal_mw"),
    ("Marine energy", "capacity_marine_mw"),
)

OPTIONAL_VARIABLES = WB_RESULT_VARS + tuple(name for _, name in CAPACITY_TECHS)


def attach_optional(
    con: Any,
    countries: list[str] | None = None,
    years: list[int] | None = None,
) -> int:
    """Write intensity and capacity variables for IEA country-years.

    Existing optional rows in scope are replaced. IEA identities are not
    recalculated. A ratio is omitted when its denominator is zero or missing.
    """
    extra, params = _scope("", countries, years)
    placeholders = ", ".join("?" for _ in OPTIONAL_VARIABLES)
    con.execute(
        "DELETE FROM results WHERE method_version = ? AND variable IN"
        f" ({placeholders})" + extra,
        [METHOD_VERSION, *OPTIONAL_VARIABLES, *params],
    )
    if con.execute("SELECT count(*) FROM wb_indicators").fetchone()[0]:
        _attach_wb(con, countries, years)
    if con.execute("SELECT count(*) FROM capacity").fetchone()[0]:
        _attach_capacity(con, countries, years)
    extra, params = _scope("", countries, years)
    count = con.execute(
        "SELECT count(*) FROM results WHERE method_version = ? AND variable IN"
        f" ({placeholders})" + extra,
        [METHOD_VERSION, *OPTIONAL_VARIABLES, *params],
    ).fetchone()[0]
    return int(count)


def _scope(
    alias: str,
    countries: list[str] | None,
    years: list[int] | None,
) -> tuple[str, list[object]]:
    prefix = f"{alias}." if alias else ""
    clauses: list[str] = []
    params: list[object] = []
    if countries:
        placeholders = ", ".join("?" for _ in countries)
        clauses.append(f"{prefix}country IN ({placeholders})")
        params.extend(countries)
    if years:
        placeholders = ", ".join("?" for _ in years)
        clauses.append(f"{prefix}year IN ({placeholders})")
        params.extend(years)
    if not clauses:
        return "", []
    return " AND " + " AND ".join(clauses), params


def _attach_wb(
    con: Any,
    countries: list[str] | None,
    years: list[int] | None,
) -> None:
    extra, params = _scope("r", countries, years)
    base = """
        FROM results r
        INNER JOIN wb_indicators w
            ON w.country = r.country AND w.year = r.year AND w.indicator = ?
        WHERE r.variable = ? AND r.method_version = ?
    """
    copies = (
        ("SP.POP.TOTL", "population", "1", "economy_tfec_tj"),
        ("NY.GDP.MKTP.CD", "gdp_current_usd", "USD", "economy_tfec_tj"),
        ("NY.GDP.MKTP.PP.KD", "gdp_ppp_constant", "USD", "economy_tfec_tj"),
    )
    for indicator, variable, unit, source in copies:
        con.execute(
            f"""
            INSERT INTO results
            SELECT r.country, r.year, ?, w.value, ?, r.method_version
            {base}
            {extra}
            """,
            [variable, unit, indicator, source, METHOD_VERSION, *params],
        )
    ratios = (
        (
            "SP.POP.TOTL",
            "economy_tfec_per_capita_tj",
            "TJ/person",
            "economy_tfec_tj",
        ),
        (
            "SP.POP.TOTL",
            "economy_tfec_renewable_per_capita_tj",
            "TJ/person",
            "economy_tfec_renewable_tj",
        ),
        (
            "NY.GDP.MKTP.PP.KD",
            "economy_tfec_per_gdp_ppp",
            "TJ/USD",
            "economy_tfec_tj",
        ),
    )
    for indicator, variable, unit, source in ratios:
        con.execute(
            f"""
            INSERT INTO results
            SELECT r.country, r.year, ?, r.value / w.value, ?, r.method_version
            {base}
            AND w.value <> 0
            {extra}
            """,
            [variable, unit, indicator, source, METHOD_VERSION, *params],
        )


def _attach_capacity(
    con: Any,
    countries: list[str] | None,
    years: list[int] | None,
) -> None:
    extra, params = _scope("r", countries, years)
    for technology, variable in CAPACITY_TECHS:
        con.execute(
            f"""
            INSERT INTO results
            SELECT r.country, r.year, ?, sum(c.capacity_mw), 'MW', r.method_version
            FROM results r
            INNER JOIN capacity c
                ON c.country = r.country
               AND c.year = r.year
               AND c.technology = ?
            WHERE r.variable = 'economy_tfec_tj' AND r.method_version = ?
            {extra}
            GROUP BY r.country, r.year, r.method_version
            """,
            [variable, technology, METHOD_VERSION, *params],
        )
