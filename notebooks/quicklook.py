import marimo

__generated_with = "0.24.2"
app = marimo.App(width="full", app_title="Renweb", html_head_file="head.html")


@app.cell(hide_code=True)
def _():
    import marimo as mo
    import plotly.express as px

    from renweb import notebook as nbk
    from renweb.validate.checks import validate

    con = nbk.connect_read_only()
    overview = nbk.overview(con)
    all_countries = nbk.countries(con)
    all_variables = nbk.variables(con)
    bounds = nbk.year_bounds(con)
    return all_countries, all_variables, bounds, con, mo, nbk, overview, px, validate


@app.cell(hide_code=True)
def _(mo, overview):
    from pathlib import Path

    _logo = Path(__file__).resolve().parents[1] / "website" / "logo.png"
    _o = overview
    _blocks = [
        mo.hstack(
            [
                mo.image(src=_logo, alt="", width=36, height=36),
                mo.md("# Renweb"),
            ],
            justify="start",
            align="center",
            gap=0.4,
        ),
        mo.md("Renewable energy statistics from World Energy Balances."),
        mo.md(
            "[Project](https://glenwright.earth/IEA-Renweb/) · "
            "[GitHub](https://github.com/glen-w/IEA-Renweb) · "
            "[Docs](https://github.com/glen-w/IEA-Renweb/blob/main/docs/METHODOLOGY.md)"
        ),
        mo.md(
            "Read-only: stop this notebook before "
            "`renweb ingest` or `renweb compute`. Shares are fractions, energy is "
            "terajoules."
        ),
        mo.md("## Warehouse"),
    ]
    if _o["sources"].empty:
        _blocks.append(mo.md("_No sources loaded. Run `uv run renweb ingest /path/to/extract`._"))
    else:
        _blocks.append(mo.ui.table(_o["sources"], selection=None))
    if _o["web_rows"]:
        _blocks.append(
            mo.md(
                f"**Balances:** {_o['web_rows']:,} rows · {_o['web_countries']} "
                f"countries · {_o['web_min_year']}–{_o['web_max_year']}"
            )
        )
        _blocks.append(mo.ui.table(_o["unit_status"], selection=None))
    if _o["results_rows"]:
        _blocks.append(
            mo.md(
                f"**Results:** {_o['results_rows']:,} rows · "
                f"{_o['results_countries']} countries · "
                f"{_o['results_min_year']}–{_o['results_max_year']} · "
                f"method_version {', '.join(_o['method_versions'])}"
            )
        )
    else:
        _blocks.append(mo.md("_No results. Run `uv run renweb compute`._"))
    _opt = _o["optional"]
    _blocks.append(
        mo.md(
            f"**Optional tables:** World Bank indicators {_opt['wb_indicators']:,} · "
            f"income groups {_opt['wb_income']:,} · IRENA capacity {_opt['capacity']:,}"
        )
    )
    mo.vstack(_blocks, gap=0.5)
    return


@app.cell(hide_code=True)
def _(all_countries, all_variables, bounds, mo, nbk):
    mo.stop(
        bounds is None,
        mo.md("_The sections below need results. Run `uv run renweb compute`, then reopen._"),
    )
    # Widgets live here; their values are read in the render cells (marimo rule).
    # Each widget is its own global: marimo binds reactivity to globals that are
    # UI elements, not to attributes of a container object.
    _controls = nbk.make_controls(mo, bounds, all_countries, all_variables)
    country_ui = _controls.country
    compare_ui = _controls.compare_countries
    variable_ui = _controls.variable
    pct_ui = _controls.pct_of_max
    year_start_ui = _controls.year_start
    year_end_ui = _controls.year_end
    map_variable_ui = _controls.map_variable
    map_year_ui = _controls.map_year
    return (
        compare_ui,
        country_ui,
        map_variable_ui,
        map_year_ui,
        pct_ui,
        variable_ui,
        year_end_ui,
        year_start_ui,
    )


@app.cell(hide_code=True)
def _(bounds, con, country_ui, mo, nbk, px, year_end_ui, year_start_ui):
    _ys, _ye = nbk.clamp_years(year_start_ui.value, year_end_ui.value, bounds)
    _country = country_ui.value
    _econ = nbk.country_series(con, _country, _ys, _ye, nbk.ECONOMY_SHARES)
    _sect = nbk.country_series(con, _country, _ys, _ye, nbk.SECTOR_SHARES)
    _stack = nbk.country_series(con, _country, _ys, _ye, nbk.TFEC_STACK)
    _econ_fig = nbk.line_chart(
        px, _econ, x="year", y="value", color="variable",
        title="Economy shares of TFEC", y_title="share (fraction)",
        empty_title="No economy shares for this selection",
    )
    _sect_fig = nbk.line_chart(
        px, _sect, x="year", y="value", color="variable",
        title="Renewable share by sector", y_title="share (fraction)",
        empty_title="No sector shares for this selection",
    )
    _stack_fig = nbk.stacked_area(
        px, _stack, title="TFEC by source (TJ)",
        empty_title="No TFEC split for this selection",
    )
    mo.vstack(
        [
            mo.md("## Country quick-look"),
            mo.hstack([country_ui, year_start_ui, year_end_ui], gap=1, wrap=True),
            mo.md(f"_{_country} · {_ys}–{_ye}_"),
            mo.ui.plotly(_econ_fig),
            mo.ui.plotly(_sect_fig),
            mo.ui.plotly(_stack_fig),
        ],
        gap=0.5,
    )
    return


@app.cell(hide_code=True)
def _(
    bounds, compare_ui, con, mo, nbk, pct_ui, px, variable_ui, year_end_ui, year_start_ui
):
    _ys, _ye = nbk.clamp_years(year_start_ui.value, year_end_ui.value, bounds)
    _picked = list(compare_ui.value or [])[: nbk.MAX_COMPARE]
    _variable = variable_ui.value or ""
    _raw = nbk.compare_series(con, _picked, _variable, _ys, _ye)
    if pct_ui.value:
        _fig = nbk.overlay_chart(
            px, nbk.normalize_pct_of_max(_raw),
            title=f"{_variable} (% of each country's max)",
            empty_title="Pick countries and a variable",
        )
    else:
        _unit = nbk.unit_label(_raw["unit"].iloc[0]) if not _raw.empty else ""
        _fig = nbk.line_chart(
            px, _raw, x="year", y="value", color="country",
            title=_variable or "Compare", y_title=_unit,
            empty_title="Pick countries and a variable",
        )
    _latest = nbk.latest_values(_raw)
    mo.vstack(
        [
            mo.md("## Compare"),
            mo.hstack(
                [compare_ui, variable_ui, pct_ui, year_start_ui, year_end_ui],
                gap=1, wrap=True,
            ),
            mo.md(f"_{len(_picked)} of {nbk.MAX_COMPARE} countries · {_ys}–{_ye}_"),
            mo.ui.plotly(_fig),
            mo.md("### Latest year per country"),
            mo.ui.table(_latest, selection=None, format_mapping=nbk.TABLE_FORMATS)
            if not _latest.empty
            else mo.md("_No data_"),
        ],
        gap=0.5,
    )
    return


@app.cell(hide_code=True)
def _(bounds, con, map_variable_ui, map_year_ui, mo, nbk, px):
    _year = nbk.clamp_years(map_year_ui.value, map_year_ui.value, bounds)[0]
    _variable = map_variable_ui.value or ""
    _frame = nbk.map_frame(con, _variable, _year)
    _fig = nbk.choropleth(
        px, _frame, title=f"{_variable} · {_year}",
        empty_title="No values for that variable and year",
    )
    mo.vstack(
        [
            mo.md("## World map"),
            mo.hstack([map_variable_ui, map_year_ui], gap=1, wrap=True),
            mo.md(
                f"_{_year} · {len(_frame)} rows. Aggregates such as WLD or OECDTOT "
                "are not ISO-3 codes and are not drawn._"
            ),
            mo.ui.plotly(_fig),
        ],
        gap=0.5,
    )
    return


@app.cell(hide_code=True)
def _(con, mo, nbk, validate):
    _findings = nbk.findings_frame(validate(con))
    _errors = int((_findings["severity"] == "error").sum()) if not _findings.empty else 0
    _body = (
        mo.md("_No findings._")
        if _findings.empty
        else mo.vstack(
            [
                mo.md(f"_{len(_findings)} finding(s), {_errors} error(s)._"),
                mo.ui.table(_findings, selection=None),
            ],
            gap=0.5,
        )
    )
    mo.vstack(
        [
            mo.md("## Validation"),
            mo.md(
                "Identities, share bounds, negative energy, and year-on-year jumps, "
                "the same checks as `renweb validate`."
            ),
            _body,
        ],
        gap=0.5,
    )
    return


if __name__ == "__main__":
    app.run()
