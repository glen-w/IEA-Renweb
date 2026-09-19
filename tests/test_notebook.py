from __future__ import annotations

import importlib.util
from pathlib import Path

import duckdb
import pytest

pd = pytest.importorskip("pandas")

from renweb import notebook as nbk  # noqa: E402
from renweb.compute.dag import compute  # noqa: E402
from renweb.ingest.pipeline import ingest  # noqa: E402
from renweb.ingest.txt import format_fixed_width  # noqa: E402
from renweb.validate.checks import Finding, validate  # noqa: E402

NOTEBOOK = Path(__file__).resolve().parent.parent / "notebooks" / "quicklook.py"


def _load(con, tmp_path: Path) -> None:
    """Two countries, two years, real ingest and compute."""
    lines = []
    for country, tfc, renew in (("FRANCE", 1000, 200), ("GERMANY", 2000, 100)):
        for year, scale in ((2021, 0.9), (2022, 1.0)):
            for product, value in (("TOTAL", tfc * scale), ("MRENEW", renew * scale)):
                lines.append(
                    format_fixed_width(country, product, year, "TFC", "TJ", value)
                )
                lines.append(
                    format_fixed_width(
                        country, product, year, "TFC", "KTOE", value / 41.868
                    )
                )
    path = tmp_path / "mini.txt"
    path.write_text("\n".join(lines) + "\n", encoding="latin-1")
    ingest(path, con)
    assert compute(con) == 4


def test_connect_read_only_needs_a_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        nbk.connect_read_only(tmp_path / "missing.duckdb")


def test_connect_read_only_reads_the_web_view(con, tmp_path: Path) -> None:
    _load(con, tmp_path)
    db = Path(con.execute("PRAGMA database_list").fetchone()[2])
    con.close()
    reader = nbk.connect_read_only(db)
    try:
        assert reader.execute("SELECT count(*) FROM web").fetchone()[0] > 0
        assert nbk.countries(reader) == ["DEU", "FRA"]
        with pytest.raises(duckdb.Error):
            reader.execute("DELETE FROM results")
    finally:
        reader.close()


def test_overview_on_an_empty_warehouse(con) -> None:
    info = nbk.overview(con)
    assert info["sources"].empty
    assert info["web_rows"] == 0
    assert info["results_rows"] == 0
    assert info["results_min_year"] is None
    assert info["method_versions"] == []
    assert info["optional"] == {"wb_indicators": 0, "wb_income": 0, "capacity": 0}
    assert nbk.year_bounds(con) is None
    assert nbk.countries(con) == []


def test_overview_after_compute(con, tmp_path: Path) -> None:
    _load(con, tmp_path)
    info = nbk.overview(con)
    assert list(info["sources"]["filename"]) == ["mini.txt"]
    assert info["web_countries"] == 2
    assert (info["web_min_year"], info["web_max_year"]) == (2021, 2022)
    assert set(info["unit_status"]["unit_status"]) == {"tj_checked"}
    assert info["results_countries"] == 2
    assert info["method_versions"] == ["2"]
    assert nbk.year_bounds(con) == (2021, 2022)
    assert "economy_share_renewable" in nbk.variables(con)


def test_country_series_is_long_and_filtered(con, tmp_path: Path) -> None:
    _load(con, tmp_path)
    frame = nbk.country_series(con, "FRA", 2022, 2022, nbk.ECONOMY_SHARES)
    assert list(frame.columns) == nbk.SERIES_COLS
    assert set(frame["year"]) == {2022}
    assert set(frame["variable"]) <= set(nbk.ECONOMY_SHARES)
    share = frame.loc[frame["variable"] == "economy_share_renewable", "value"].iloc[0]
    assert share == pytest.approx(0.2)
    assert nbk.country_series(con, "FRA", None, None, ()).empty
    assert nbk.country_series(con, "XXX", None, None, nbk.ECONOMY_SHARES).empty


def test_compare_series_caps_and_normalises(con, tmp_path: Path) -> None:
    _load(con, tmp_path)
    frame = nbk.compare_series(con, ["FRA", "DEU"], "economy_tfec_tj", 2021, 2022)
    assert list(frame.columns) == nbk.COMPARE_COLS
    assert len(frame) == 4
    norm = nbk.normalize_pct_of_max(frame)
    assert set(norm["pct_of_max"].round(6)) == {90.0, 100.0}
    latest = nbk.latest_values(frame)
    assert list(latest["country"]) == ["DEU", "FRA"]
    assert set(latest["year"]) == {2022}
    too_many = [f"C{i}" for i in range(10)]
    assert nbk.compare_series(con, too_many, "economy_tfec_tj", None, None).empty
    assert nbk.compare_series(con, [], "economy_tfec_tj", None, None).empty
    assert nbk.compare_series(con, ["FRA"], "", None, None).empty


def test_normalize_pct_of_max_handles_zero_and_empty() -> None:
    empty = nbk.normalize_pct_of_max(pd.DataFrame(columns=nbk.COMPARE_COLS))
    assert "pct_of_max" in empty.columns and empty.empty
    zeros = pd.DataFrame(
        {"year": [2020, 2021], "country": ["A", "A"], "value": [0.0, 0.0], "unit": "TJ"}
    )
    assert list(nbk.normalize_pct_of_max(zeros)["pct_of_max"]) == [0.0, 0.0]


def test_map_frame(con, tmp_path: Path) -> None:
    _load(con, tmp_path)
    frame = nbk.map_frame(con, "economy_share_renewable", 2022)
    assert list(frame.columns) == nbk.MAP_COLS
    assert list(frame["country"]) == ["DEU", "FRA"]
    assert nbk.map_frame(con, "economy_share_renewable", 1999).empty


def test_findings_frame_and_clamp() -> None:
    frame = nbk.findings_frame(
        [Finding("warning", "share_bounds", "too high", "FRA", 2022, "x_share")]
    )
    assert list(frame.columns) == nbk.FINDING_COLS
    assert frame.iloc[0]["year"] == "2022"
    assert nbk.findings_frame([]).empty
    assert nbk.clamp_years(1990, 2030, (2000, 2010)) == (2000, 2010)
    assert nbk.clamp_years(2008, 2003, (2000, 2010)) == (2003, 2008)
    assert nbk.unit_label("1") == "share (fraction)"
    assert nbk.unit_label("TJ") == "TJ"
    assert nbk.unit_label(None) == ""


def test_charts_return_figures() -> None:
    px = pytest.importorskip("plotly.express")
    frame = pd.DataFrame(
        {
            "year": [2020, 2021, 2020, 2021],
            "country": ["FRA", "FRA", "DEU", "DEU"],
            "value": [1.0, 2.0, 4.0, 3.0],
            "unit": ["TJ"] * 4,
        }
    )
    line = nbk.line_chart(
        px, frame, x="year", y="value", color="country", title="t", y_title="TJ"
    )
    assert len(line.data) == 2
    overlay = nbk.overlay_chart(px, nbk.normalize_pct_of_max(frame), title="t")
    assert len(overlay.data) == 2
    stack = nbk.stacked_area(
        px, frame.rename(columns={"country": "variable"}), title="t"
    )
    assert len(stack.data) == 2
    world = nbk.choropleth(px, frame.drop(columns=["year", "unit"]), title="t")
    assert len(world.data) == 1
    empty = pd.DataFrame(columns=nbk.COMPARE_COLS)
    assert (
        nbk.line_chart(
            px, empty, x="year", y="value", color="country", title="t", y_title="TJ"
        ).layout.title.text
        == "t"
    )
    assert (
        nbk.overlay_chart(px, empty, title="t", empty_title="e").layout.title.text
        == "e"
    )
    assert nbk.choropleth(px, empty, title="t").layout.title.text == "t"


def test_make_controls_with_a_fake_mo() -> None:
    class _Widget:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.value = kwargs.get("value")

    class _UI:
        def dropdown(self, **kwargs):
            return _Widget(**kwargs)

        def multiselect(self, **kwargs):
            if "max_selections" in kwargs:
                raise TypeError("old marimo")
            return _Widget(**kwargs)

        def slider(self, **kwargs):
            assert kwargs["stop"] > kwargs["start"]
            return _Widget(**kwargs)

        def switch(self, **kwargs):
            return _Widget(**kwargs)

    class _Mo:
        ui = _UI()

    controls = nbk.make_controls(
        _Mo(), (2022, 2022), ["WLD", "FRA", "DEU"], ["economy_share_renewable", "x_tj"]
    )
    assert controls.country.value == "WLD"
    assert controls.compare_countries.value == ["DEU", "FRA"]
    assert controls.variable.value == "economy_share_renewable"
    assert controls.map_variable.kwargs["options"] == ["economy_share_renewable"]
    assert controls.year_start.kwargs["stop"] == 2023


def test_notebook_file_loads() -> None:
    pytest.importorskip("marimo")
    spec = importlib.util.spec_from_file_location("renweb_notebook", NOTEBOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "app")


def test_validate_runs_read_only(con, tmp_path: Path) -> None:
    _load(con, tmp_path)
    db = Path(con.execute("PRAGMA database_list").fetchone()[2])
    con.close()
    reader = nbk.connect_read_only(db)
    try:
        frame = nbk.findings_frame(validate(reader))
        assert list(frame.columns) == nbk.FINDING_COLS
    finally:
        reader.close()


def test_open_year_range_and_cap_with_real_rows(con, tmp_path: Path) -> None:
    _load(con, tmp_path)
    both = nbk.country_series(con, "FRA", None, None, ("economy_tfec_tj",))
    assert sorted(both["year"]) == [2021, 2022]
    only_2021 = nbk.country_series(con, "FRA", None, 2021, ("economy_tfec_tj",))
    assert list(only_2021["year"]) == [2021]
    # FRA is the seventh pick, so the cap of six drops it even though it exists.
    padded = [f"X{i}" for i in range(nbk.MAX_COMPARE)] + ["FRA"]
    assert nbk.compare_series(con, padded, "economy_tfec_tj", None, None).empty
    kept = ["FRA"] + [f"X{i}" for i in range(nbk.MAX_COMPARE)]
    assert len(nbk.compare_series(con, kept, "economy_tfec_tj", None, None)) == 2


def test_overview_tolerates_an_older_warehouse(con, tmp_path: Path) -> None:
    """A warehouse from before the IRENA extra has no ``capacity`` table."""
    _load(con, tmp_path)
    con.execute("DROP TABLE capacity")
    info = nbk.overview(con)
    assert info["optional"]["capacity"] == 0
    assert info["optional"]["wb_indicators"] == 0
    assert info["results_rows"] > 0


def test_normalize_coerces_bad_values_and_latest_handles_no_year() -> None:
    frame = pd.DataFrame(
        {
            "year": [2020, 2021, 2022],
            "country": ["A", "A", "A"],
            "value": [None, "oops", 50.0],
            "unit": "TJ",
        }
    )
    norm = nbk.normalize_pct_of_max(frame)
    assert list(norm["pct_of_max"]) == [0.0, 0.0, 100.0]
    no_year = pd.DataFrame({"country": ["A"], "value": [1.0]})
    assert nbk.latest_values(no_year).equals(no_year)
    assert nbk.latest_values(pd.DataFrame(columns=nbk.COMPARE_COLS)).empty


def test_default_compare_prefers_large_economies() -> None:
    full = ["AFRICA", "AGO", "ALB", "BRA", "CHN", "DEU", "FRA", "IND", "USA", "WLD"]
    assert nbk.default_compare_countries(full) == ["CHN", "USA", "IND"]
    # Top up in list order when the preferred codes are missing; skip WLD.
    assert nbk.default_compare_countries(["WLD", "NOR", "FRA", "SWE"]) == [
        "FRA",
        "NOR",
        "SWE",
    ]
    assert nbk.default_compare_countries(["WLD"]) == ["WLD"]
    assert nbk.default_compare_countries([]) == []
    assert nbk.default_compare_countries(full, count=6) == [
        "CHN",
        "USA",
        "IND",
        "DEU",
        "FRA",
        "BRA",
    ]


def test_make_controls_accepts_reversed_bounds() -> None:
    class _Widget:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.value = kwargs.get("value")

    class _UI:
        def __getattr__(self, name):
            return lambda **kwargs: _Widget(**kwargs)

    class _Mo:
        ui = _UI()

    controls = nbk.make_controls(_Mo(), (2022, 2015), ["FRA"], ["x_tj"])
    assert controls.year_start.kwargs["start"] == 2015
    assert controls.year_start.kwargs["stop"] == 2022
    assert controls.year_end.value == 2022
    assert controls.country.value == "FRA"
    # No share variable: the map falls back to whatever variables exist.
    assert controls.map_variable.kwargs["options"] == ["x_tj"]


def test_empty_frames_give_titled_empty_figures() -> None:
    px = pytest.importorskip("plotly.express")
    empty = pd.DataFrame(columns=nbk.SERIES_COLS)
    assert (
        nbk.stacked_area(px, empty, title="t", empty_title="e").layout.title.text == "e"
    )
    all_nan = pd.DataFrame({"country": ["FRA", "DEU"], "value": [None, None]})
    world = nbk.choropleth(px, all_nan, title="t", empty_title="e")
    assert world.layout.title.text == "e"
    # plotly's empty choropleth carries one trace with no data.
    assert all(len(trace.z or []) == 0 for trace in world.data)
    wrong_cols = pd.DataFrame({"a": [1]})
    assert (
        nbk.line_chart(
            px, wrong_cols, x="year", y="value", color="country", title="t", y_title=""
        ).layout.title.text
        == "t"
    )


def _run_notebook_headless():
    spec = importlib.util.spec_from_file_location("renweb_quicklook", NOTEBOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app.run()


def test_notebook_runs_headless_on_a_populated_warehouse(con, tmp_path: Path) -> None:
    pytest.importorskip("marimo")
    pytest.importorskip("plotly")
    _load(con, tmp_path)
    con.close()  # The fixture's RENWEB_DATA points the notebook at this file.
    outputs, defs = _run_notebook_headless()
    assert len(outputs) == 7
    assert defs["bounds"] == (2021, 2022)
    assert defs["country_ui"].value == "DEU"
    assert set(defs["compare_ui"].value) == {"DEU", "FRA"}
    assert defs["overview"]["results_countries"] == 2
    rendered = [out for out in outputs if out is not None]
    assert len(rendered) == 5  # overview, country, compare, map, validation
    defs["con"].close()


def test_notebook_runs_headless_on_an_empty_warehouse(con) -> None:
    pytest.importorskip("marimo")
    pytest.importorskip("plotly")
    con.close()
    outputs, defs = _run_notebook_headless()
    assert defs["bounds"] is None
    assert "country_ui" not in defs  # mo.stop halted the controls cell
    rendered = [out for out in outputs if out is not None]
    assert len(rendered) == 3  # overview, the stop message, validation
    defs["con"].close()
