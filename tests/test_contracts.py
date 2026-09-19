"""Contracts the default suite did not pin down: replacement, units, checks, CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from renweb import __version__
from renweb.cli import app
from renweb.compute.dag import compute
from renweb.compute.formulas import Frame, _add, _first, adjustment_multipliers
from renweb.export.writers import ExportError, export_results
from renweb.ingest.pipeline import IngestError, ingest
from renweb.ingest.txt import format_fixed_width, parse_line
from renweb.refdata.codes import GWH_TO_TJ, KTOE_TO_TJ
from renweb.validate.checks import validate
from renweb.warehouse import connect, warehouse_path

runner = CliRunner()


def _pair(flow: str, tj: float) -> list[str]:
    return [
        format_fixed_width("FRANCE", "TOTAL", 2022, flow, "TJ", tj),
        format_fixed_width("FRANCE", "TOTAL", 2022, flow, "KTOE", tj / KTOE_TO_TJ),
    ]


def test_vendored_tables_ship_beside_the_package() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "renweb" / "refdata" / "data"
    names = {path.name for path in root.iterdir()}
    assert {
        "code_crosswalk.csv",
        "country_crosswalk.csv",
        "iea_codes.json",
        "iea_regions.json",
        "oecd_members.json",
        "adjustment_factors.json",
        "conversion_factors.json",
        "fossil_fuels.json",
    } <= names


def test_blank_short_and_flagged_values() -> None:
    blank = parse_line(format_fixed_width("FRANCE", "TOTAL", 2022, "TFC", "TJ", ""))
    assert blank is not None and blank["value"] is None
    assert parse_line("") is None
    assert parse_line("too short") is None
    flagged = parse_line(
        format_fixed_width("FRANCE", "TOTAL", 2022, "TFC", "TJ", "12.5M")
    )
    assert flagged is not None
    assert flagged["value"] == pytest.approx(12.5)
    assert flagged["flag"] == "M"


def test_duplicate_codes_and_non_finite_results() -> None:
    frame = Frame.from_pairs({("TFC", "AGRICULT"): 3.0, ("TFC", "AGRI_FOREST"): 4.0})
    assert frame.get_sum("TFC", ("AGRICULT", "AGRI_FOREST")) == pytest.approx(7)
    assert frame.flow_abs(("IMPORTS", "IMPORTS"), "ELECTR") == 0
    assert (
        _first(Frame.from_pairs({("SUPPLY", "TOTAL"): 5}), ("TES", "SUPPLY"), "TOTAL")
        == 5
    )
    out: dict[str, tuple[float, str]] = {}
    _add(out, "dropped", float("nan"), "TJ")
    assert out == {}


def test_multiplier_outside_bounds_uses_the_fallback() -> None:
    frame = Frame.from_pairs({("IMPORTS", "ELECTR"): 1, ("LOSSES", "ELECTR"): 100})
    multipliers, fallback = adjustment_multipliers(frame)
    assert fallback is True
    assert multipliers["hydropower"] == pytest.approx(0.99)


def test_single_unit_rows_unmapped_country_and_replacement(con, tmp_path: Path) -> None:
    path = tmp_path / "WORLDBIG.TXT"
    lines = [
        format_fixed_width("FRANCE", "TOTAL", 2022, "TFC", "KTOE", 2),
        format_fixed_width("FRANCE", "TOTAL", 2022, "ELOUTPUT", "GWH", 10),
        format_fixed_width("ZZZLAND", "TOTAL", 2022, "TES", "TJ", 7),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="latin-1")
    report = ingest(path, con)[0]
    assert report.unmapped_countries == 1
    ktoe = con.execute(
        "SELECT value_tj, unit_status FROM web WHERE flow = 'TFC'"
    ).fetchone()
    assert ktoe[1] == "from_ktoe"
    assert ktoe[0] == pytest.approx(2 * KTOE_TO_TJ)
    gwh = con.execute(
        "SELECT value_tj, unit_status FROM web WHERE flow = 'ELOUTPUT'"
    ).fetchone()
    assert gwh[1] == "from_gwh"
    assert gwh[0] == pytest.approx(10 * GWH_TO_TJ)
    kept = con.execute(
        "SELECT country, mapped FROM web_raw WHERE iea_country = 'ZZZLAND'"
    ).fetchone()
    assert kept == ("ZZZLAND", False)

    path.write_text("\n".join(_pair("TFC", 50)) + "\n", encoding="latin-1")
    replaced = ingest(path, con)[0]
    assert replaced.skipped_existing is False
    assert replaced.rows_stored == 2
    rows = con.execute("SELECT count(*) FROM web_raw").fetchone()[0]
    assert rows == 2
    status = con.execute("SELECT unit_status FROM web WHERE flow = 'TFC'").fetchone()[0]
    assert status == "tj_checked"


def test_directory_empty_and_header_sniff(con, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(IngestError, match="No balances files"):
        ingest(empty, con)
    with pytest.raises(IngestError, match="No such file"):
        ingest(tmp_path / "missing.txt", con)
    blank = tmp_path / "blank.txt"
    blank.write_text("\n", encoding="latin-1")
    with pytest.raises(IngestError, match="no balances records"):
        ingest(blank, con)

    folder = tmp_path / "extract"
    folder.mkdir()
    (folder / "part.txt").write_text(
        "\n".join(_pair("TFC", 80)) + "\n", encoding="latin-1"
    )
    sniffed = folder / "WORLDBIG"
    sniffed.write_text(
        "COUNTRY,ENERGY_BALANCE_FLOW,ENERGY_PRODUCT,TIME_PERIOD,OBS_VALUE,UNIT\n"
        "FRANCE,TES,TOTAL,2020,4,TJ\n",
        encoding="utf-8",
    )
    reports = ingest(folder, con)
    assert {report.format for report in reports} == {"txt", "csv"}
    assert compute(con, countries=["FRA"]) == 2


def test_suspect_rows_are_not_computed(con, tmp_path: Path) -> None:
    path = tmp_path / "bad.txt"
    path.write_text(
        "\n".join(
            [
                format_fixed_width("FRANCE", "TOTAL", 2022, "TFC", "TJ", 1000),
                format_fixed_width("FRANCE", "TOTAL", 2022, "TFC", "KTOE", 10),
            ]
        )
        + "\n",
        encoding="latin-1",
    )
    ingest(path, con)
    assert compute(con) == 0


def test_identity_and_share_group_findings(con) -> None:
    con.execute("""
        INSERT INTO results VALUES
            ('FRA', 2022, 'adjusted_tfec_tj', 10, 'TJ', '2'),
            ('FRA', 2022, 'raw_tfc_total_tj', 100, 'TJ', '2'),
            ('FRA', 2022, 'raw_non_energy_use_tj', 5, 'TJ', '2'),
            ('FRA', 2022, 'economy_share_fossil', 0.9, '1', '2'),
            ('FRA', 2022, 'economy_share_nuclear', 0.9, '1', '2'),
            ('FRA', 2022, 'economy_share_renewable', 0.9, '1', '2'),
            ('FRA', 2022, 'power_output_tj', -5, 'TJ', '2')
        """)
    checks = {item.check for item in validate(con)}
    assert "tfec_identity" in checks
    assert "tfec_shares" in checks
    assert "non_negative" in checks


def test_export_rejects_empty_and_unknown_formats(con, tmp_path: Path) -> None:
    with pytest.raises(ExportError, match="No results"):
        export_results(con, tmp_path / "out", ["csv"])
    con.execute(
        "INSERT INTO results VALUES ('FRA', 2022, 'economy_tfec_tj', 1, 'TJ', '1')"
    )
    with pytest.raises(ExportError, match="Unknown format"):
        export_results(con, tmp_path / "out", ["json"])
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        with pytest.raises(ExportError, match="xlsx extra"):
            export_results(con, tmp_path / "out", ["xlsx"])
    else:
        written = export_results(con, tmp_path / "xlsx", ["xlsx"])
        assert written[0].is_file()


def test_renweb_data_file_and_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RENWEB_DATA", str(tmp_path / "custom.duckdb"))
    assert warehouse_path() == tmp_path / "custom.duckdb"
    monkeypatch.setenv("RENWEB_DATA", str(tmp_path / "store"))
    assert warehouse_path() == tmp_path / "store" / "renweb.duckdb"
    database = connect()
    database.close()


def test_cli_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RENWEB_DATA", str(tmp_path / "cli.duckdb"))
    version = runner.invoke(app, ["--version"])
    assert version.exit_code == 0
    assert __version__ in version.stdout

    missing = runner.invoke(app, ["ingest", str(tmp_path / "missing.txt")])
    assert missing.exit_code == 1
    empty = runner.invoke(app, ["compute"])
    assert empty.exit_code == 1
    assert "Nothing to compute" in empty.stdout

    path = tmp_path / "mini.txt"
    path.write_text("\n".join(_pair("TFC", 40)) + "\n", encoding="latin-1")
    loaded = runner.invoke(app, ["ingest", str(path)])
    assert loaded.exit_code == 0
    done = runner.invoke(app, ["compute", "--country", "FRA", "--year", "2022"])
    assert done.exit_code == 0
    quiet = runner.invoke(app, ["validate"])
    assert quiet.exit_code == 0
    exported = runner.invoke(app, ["export", str(tmp_path / "out")])
    assert exported.exit_code == 0
    assert (tmp_path / "out" / "results.csv").is_file()

    database = connect(tmp_path / "cli.duckdb")
    database.execute("UPDATE results SET value = 0 WHERE variable = 'adjusted_tfec_tj'")
    database.close()
    broken = runner.invoke(app, ["validate"])
    assert broken.exit_code == 1
