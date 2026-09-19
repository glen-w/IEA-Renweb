"""Optional World Bank and IRENA lanes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from renweb.cli import app
from renweb.compute.dag import compute
from renweb.ingest.http import request_json
from renweb.ingest.irena import (
    IRENA_FOLDER,
    decode_jsonstat2,
    discover_capacity_table,
    ingest_irena,
)
from renweb.ingest.pipeline import IngestError, ingest
from renweb.ingest.txt import format_fixed_width
from renweb.ingest.worldbank import ingest_worldbank
from renweb.refdata.codes import KTOE_TO_TJ
from renweb.validate.checks import validate

runner = CliRunner()


def _balances(tmp_path: Path, tj: float = 40.0) -> Path:
    path = tmp_path / "mini.txt"
    path.write_text(
        "\n".join(
            [
                format_fixed_width("FRANCE", "TOTAL", 2022, "TFC", "TJ", tj),
                format_fixed_width(
                    "FRANCE", "TOTAL", 2022, "TFC", "KTOE", tj / KTOE_TO_TJ
                ),
            ]
        )
        + "\n",
        encoding="latin-1",
    )
    return path


def _wb_fetch(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    del method, params, json_body
    if "/indicator/SP.POP.TOTL" in url:
        return [
            {"page": 1, "pages": 1},
            [
                {
                    "countryiso3code": "FRA",
                    "date": "2022",
                    "value": 10,
                    "indicator": {"id": "SP.POP.TOTL"},
                }
            ],
        ]
    if "/indicator/NY.GDP.MKTP.CD" in url:
        return [
            {"page": 1, "pages": 1},
            [
                {
                    "countryiso3code": "FRA",
                    "date": "2022",
                    "value": 1000,
                    "indicator": {"id": "NY.GDP.MKTP.CD"},
                }
            ],
        ]
    if "/indicator/NY.GDP.MKTP.PP.KD" in url:
        return [
            {"page": 1, "pages": 1},
            [
                {
                    "countryiso3code": "FRA",
                    "date": "2022",
                    "value": 20,
                    "indicator": {"id": "NY.GDP.MKTP.PP.KD"},
                }
            ],
        ]
    if url.rstrip("/").endswith("/country"):
        return [
            {"page": 1, "pages": 1},
            [
                {
                    "id": "FRA",
                    "region": {"id": "ECS"},
                    "incomeLevel": {"id": "HIC", "value": "High income"},
                },
                {
                    "id": "WLD",
                    "region": {"id": "NA"},
                    "incomeLevel": {"id": "INX", "value": "Not classified"},
                },
            ],
        ]
    raise AssertionError(url)


def _irena_stat() -> dict[str, Any]:
    return {
        "id": ["Country/area", "Technology", "Grid connection", "Year"],
        "size": [1, 2, 2, 1],
        "dimension": {
            "Country/area": {
                "category": {
                    "index": {"FRA": 0},
                    "label": {"FRA": "France"},
                }
            },
            "Technology": {
                "category": {
                    "index": {"0": 0, "2": 1},
                    "label": {
                        "0": "Total renewable energy",
                        "2": "Solar photovoltaic",
                    },
                }
            },
            "Grid connection": {
                "category": {
                    "index": {"0": 0, "1": 1},
                    "label": {"0": "OnGrid", "1": "OffGrid"},
                }
            },
            "Year": {
                "category": {
                    "index": {"22": 0},
                    "label": {"22": "2022"},
                }
            },
        },
        "value": [10, 5, 3, 0],
    }


def _irena_fetch(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    del params
    if method == "GET" and url.rstrip("/") == IRENA_FOLDER:
        return [
            {
                "id": "Region_ELECCAP_2026_H1_v-PX 1.px",
                "type": "t",
            },
            {
                "id": "Country_ELECCAP_2026_H1_v-PX 1.px",
                "type": "t",
            },
        ]
    if method == "GET" and "Country_ELECCAP" in url:
        return {
            "variables": [
                {
                    "code": "Year",
                    "values": ["22"],
                    "valueTexts": ["2022"],
                }
            ]
        }
    if method == "POST" and "Country_ELECCAP" in url:
        assert json_body is not None
        return _irena_stat()
    raise AssertionError((method, url))


def test_missing_httpx_names_the_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> None:
        raise IngestError("httpx is not installed")

    monkeypatch.setattr("renweb.ingest.http._load_httpx", fail)
    with pytest.raises(IngestError, match="worldbank extra"):
        request_json("worldbank", "World Bank", "GET", "https://example.test")
    with pytest.raises(IngestError, match="irena extra"):
        request_json("irena", "IRENA", "GET", "https://example.test")


def test_cli_optional_ingest_needs_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RENWEB_DATA", str(tmp_path / "cli.duckdb"))

    def wb_fail(*_args: object, **_kwargs: object) -> None:
        raise IngestError(
            "World Bank ingest needs the worldbank extra: uv sync --extra worldbank"
        )

    def irena_fail(*_args: object, **_kwargs: object) -> None:
        raise IngestError("IRENA ingest needs the irena extra: uv sync --extra irena")

    monkeypatch.setattr("renweb.ingest.worldbank._default_fetch", wb_fail)
    monkeypatch.setattr("renweb.ingest.irena._default_fetch", irena_fail)
    worldbank = runner.invoke(app, ["ingest-worldbank"])
    assert worldbank.exit_code == 1
    assert "worldbank extra" in worldbank.stdout
    irena = runner.invoke(app, ["ingest-irena"])
    assert irena.exit_code == 1
    assert "irena extra" in irena.stdout


def test_worldbank_attaches_intensity_and_keeps_identity(con, tmp_path: Path) -> None:
    ingest(_balances(tmp_path), con)
    compute(con, countries=["FRA"], years=[2022])
    report = ingest_worldbank(con, fetch=_wb_fetch)
    assert report.indicators == 3
    assert report.income_rows == 1
    assert report.attached > 0
    pop = con.execute(
        "SELECT value, unit FROM results "
        "WHERE country = 'FRA' AND year = 2022 AND variable = 'population'"
    ).fetchone()
    assert pop == (10, "1")
    income = con.execute(
        "SELECT income_level_id FROM wb_income WHERE country = 'FRA'"
    ).fetchone()
    assert income == ("HIC",)
    tfec = con.execute(
        "SELECT value FROM results "
        "WHERE country = 'FRA' AND year = 2022 AND variable = 'economy_tfec_tj'"
    ).fetchone()[0]
    per_capita = con.execute(
        "SELECT value FROM results WHERE variable = 'economy_tfec_per_capita_tj'"
    ).fetchone()[0]
    per_gdp = con.execute(
        "SELECT value FROM results WHERE variable = 'economy_tfec_per_gdp_ppp'"
    ).fetchone()[0]
    assert per_capita == pytest.approx(tfec / 10)
    assert per_gdp == pytest.approx(tfec / 20)
    ingest_worldbank(con, fetch=_wb_fetch)
    copies = con.execute(
        "SELECT count(*) FROM results WHERE variable = 'population' "
        "AND country = 'FRA' AND year = 2022"
    ).fetchone()[0]
    assert copies == 1
    compute(con, countries=["FRA"], years=[2022])
    assert (
        con.execute(
            "SELECT count(*) FROM results WHERE variable = 'population' "
            "AND country = 'FRA' AND year = 2022"
        ).fetchone()[0]
        == 1
    )
    findings = [item for item in validate(con) if item.severity == "error"]
    assert findings == []


def test_worldbank_omits_ratio_when_population_is_zero(con, tmp_path: Path) -> None:
    ingest(_balances(tmp_path), con)
    compute(con)

    def fetch(
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        payload = _wb_fetch(method, url, params=params, json_body=json_body)
        if "/indicator/SP.POP.TOTL" in url:
            payload[1][0]["value"] = 0
        return payload

    ingest_worldbank(con, fetch=fetch)
    missing = con.execute(
        "SELECT count(*) FROM results WHERE variable = 'economy_tfec_per_capita_tj'"
    ).fetchone()[0]
    assert missing == 0


def test_irena_csv_and_api_capacity(con, tmp_path: Path) -> None:
    ingest(_balances(tmp_path), con)
    compute(con, countries=["FRA"], years=[2022])
    csv_path = tmp_path / "capacity.csv"
    csv_path.write_text(
        "country,year,technology,grid,capacity_mw\n"
        "fra,2022,Total renewable energy,OnGrid,10\n"
        "FRA,2022,Total renewable energy,OffGrid,5\n"
        "FRA,2022,Solar photovoltaic,OnGrid,3\n",
        encoding="utf-8",
    )
    csv_report = ingest_irena(con, csv_path)
    assert csv_report.rows == 3
    renewable = con.execute(
        "SELECT value FROM results WHERE variable = 'capacity_renewable_mw'"
    ).fetchone()[0]
    assert renewable == pytest.approx(15)
    solar = con.execute(
        "SELECT value FROM results WHERE variable = 'capacity_solar_pv_mw'"
    ).fetchone()[0]
    assert solar == pytest.approx(3)
    api_report = ingest_irena(con, fetch=_irena_fetch)
    assert api_report.table == "Country_ELECCAP_2026_H1_v-PX 1.px"
    assert api_report.rows == 4
    assert con.execute(
        "SELECT value FROM results WHERE variable = 'capacity_renewable_mw'"
    ).fetchone()[0] == pytest.approx(15)
    findings = [item for item in validate(con) if item.severity == "error"]
    assert findings == []


def test_discover_capacity_table_and_jsonstat() -> None:
    table = discover_capacity_table(
        [
            {"id": "Country_ELECCAP_2025_H2_v-PX 1.px"},
            {"id": "Region_ELECCAP_2026_H1_v-PX 1.px"},
            {"id": "Country_ELECCAP_2026_H1_v-PX 1.px"},
        ]
    )
    assert table == "Country_ELECCAP_2026_H1_v-PX 1.px"
    rows = decode_jsonstat2(_irena_stat())
    assert ("FRA", 2022, "Total renewable energy", "OnGrid", 10.0) in rows
    assert ("FRA", 2022, "Solar photovoltaic", "OffGrid", 0.0) in rows


def test_warehouse_has_optional_tables(con) -> None:
    for table in ("wb_indicators", "wb_income", "capacity"):
        con.execute(f"SELECT * FROM {table} LIMIT 0")


def test_attach_optional_skips_empty_tables(con, tmp_path: Path) -> None:
    from renweb.compute.optional import attach_optional

    ingest(_balances(tmp_path), con)
    compute(con)
    assert attach_optional(con) == 0
    assert (
        con.execute(
            "SELECT count(*) FROM results WHERE variable IN ('population', 'capacity_renewable_mw')"
        ).fetchone()[0]
        == 0
    )


def test_worldbank_forwards_date_range_and_pages(con, tmp_path: Path) -> None:
    ingest(_balances(tmp_path), con)
    compute(con)
    pop_pages: list[int] = []

    def fetch(
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        if "/indicator/SP.POP.TOTL" in url:
            page = int((params or {}).get("page") or 1)
            pop_pages.append(page)
            assert (params or {}).get("date") == "2020:2022"
            if page == 1:
                return [
                    {"page": 1, "pages": 2},
                    [
                        {
                            "countryiso3code": "FRA",
                            "date": "2022",
                            "value": 10,
                            "indicator": {"id": "SP.POP.TOTL"},
                        }
                    ],
                ]
            return [{"page": 2, "pages": 2}, []]
        return _wb_fetch(method, url, params=params, json_body=json_body)

    ingest_worldbank(con, start_year=2020, end_year=2022, fetch=fetch)
    assert pop_pages == [1, 2]


def test_irena_missing_csv_and_cli_csv(
    con, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(IngestError, match="No such file"):
        ingest_irena(con, tmp_path / "missing.csv")
    monkeypatch.setenv("RENWEB_DATA", str(tmp_path / "cli.duckdb"))
    csv_path = tmp_path / "capacity.csv"
    csv_path.write_text(
        "country,year,technology,grid,capacity_mw\n"
        "FRA,2022,Total renewable energy,OnGrid,8\n",
        encoding="utf-8",
    )
    loaded = runner.invoke(app, ["ingest-irena", str(csv_path)])
    assert loaded.exit_code == 0
    assert "1 capacity rows" in loaded.stdout
    assert "Attached 0" in loaded.stdout
