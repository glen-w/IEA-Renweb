from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from renweb.compute.dag import compute
from renweb.ingest.pipeline import ingest
from renweb.ingest.txt import format_fixed_width

FRANCE_TFC_TJ = "FRANCE          TOTAL           2022            TFC             TJ                      5902969.0981 "
FRANCE_TFC_KTOE = "FRANCE          TOTAL           2022            TFC             KTOE                     140989.9947 "
FRANCE_HYDRO_TJ = "FRANCE          HYDRO           2022            ELOUTPUT        TJ                        45521.1320 "
FRANCE_HYDRO_KTOE = "FRANCE          HYDRO           2022            ELOUTPUT        KTOE                      45521.1320 "


def _write(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="latin-1")


def test_layout_lines_are_101_characters() -> None:
    for line in (FRANCE_TFC_TJ, FRANCE_TFC_KTOE, FRANCE_HYDRO_TJ, FRANCE_HYDRO_KTOE):
        assert len(line) == 101


def test_ingest_checks_units_and_skips_a_second_time(con, tmp_path: Path) -> None:
    suspect_tj = format_fixed_width("FRANCE", "TOTAL", 2022, "TES", "TJ", 1000)
    suspect_ktoe = format_fixed_width("FRANCE", "TOTAL", 2022, "TES", "KTOE", 10)
    duplicate_low = format_fixed_width("FRANCE", "WIND", 2022, "ELOUTPUT", "TJ", 1)
    duplicate_high = format_fixed_width("FRANCE", "WIND", 2022, "ELOUTPUT", "TJ", 5)
    missing = format_fixed_width("FRANCE", "TOTAL", 2022, "IMPORTS", "TJ", "..")
    path = tmp_path / "WORLDBIG.TXT"
    _write(
        path,
        [
            FRANCE_TFC_TJ,
            FRANCE_TFC_KTOE,
            FRANCE_HYDRO_TJ,
            FRANCE_HYDRO_KTOE,
            suspect_tj,
            suspect_ktoe,
            duplicate_low,
            duplicate_high,
            missing,
        ],
    )
    report = ingest(path, con)[0]
    assert report.rows_stored == 8
    assert report.duplicates_dropped == 1
    assert report.null_values == 1
    assert report.unmapped_countries == 0

    tfc = con.execute("""
        SELECT value_tj, unit_status FROM web
        WHERE country = 'FRA' AND flow = 'TFC' AND product = 'TOTAL' AND year = 2022
        """).fetchone()
    assert tfc[1] == "tj_checked"
    assert tfc[0] == pytest.approx(5_902_969.0981)

    hydro = con.execute("""
        SELECT value_tj, unit_status FROM web
        WHERE country = 'FRA' AND flow = 'ELOUTPUT' AND product = 'HYDRO' AND year = 2022
        """).fetchone()
    assert hydro[1] == "electricity_output_gwh"
    assert hydro[0] == pytest.approx(45521.1320 * 3.6)

    suspect = con.execute("""
        SELECT value_tj, unit_status FROM web
        WHERE country = 'FRA' AND flow = 'TES' AND product = 'TOTAL' AND year = 2022
        """).fetchone()
    assert suspect[1] == "suspect"
    assert suspect[0] is None

    again = ingest(path, con)[0]
    assert again.skipped_existing is True


def test_zip_and_csv(con, tmp_path: Path) -> None:
    txt = tmp_path / "WORLDBIG1.TXT"
    _write(txt, [FRANCE_TFC_TJ, FRANCE_TFC_KTOE])
    archive = tmp_path / "WBIG.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.write(txt, arcname="WORLDBIG1.TXT")
    report = ingest(archive, con)[0]
    assert report.rows_stored == 2
    assert report.filename.endswith("WORLDBIG1.TXT")

    csv_path = tmp_path / "balances.csv"
    csv_path.write_text(
        "COUNTRY,ENERGY_BALANCE_FLOW,ENERGY_PRODUCT,TIME_PERIOD,OBS_VALUE,UNIT,QUALIFIER\n"
        "NIGERIA,TFC,TOTAL,2021,10,TJ,I\n"
        "NIGERIA,TFC,TOTAL,2021,,TJ,O\n",
        encoding="utf-8",
    )
    # The empty observation is a second row of the same key; max() keeps 10.
    csv_report = ingest(csv_path, con)[0]
    assert csv_report.format == "csv"
    assert csv_report.rows_stored == 1
    row = con.execute("""
        SELECT value_tj, unit_status FROM web
        WHERE country = 'NGA' AND year = 2021 AND flow = 'TFC'
        """).fetchone()
    assert row[1] == "tj_unchecked"
    assert row[0] == pytest.approx(10)
    assert compute(con, countries=["NGA"], years=[2021]) == 1


def test_oecd_long_csv_uses_measure_as_unit(con, tmp_path: Path) -> None:
    """The older OECD iLibrary extract names the unit column MEASURE."""
    path = tmp_path / "WBIG.csv"
    path.write_text(
        "COUNTRY,PRODUCT,FLOW,TIME,Value,MEASURE,Flag Codes\n"
        "FRANCE,TOTAL,TFC,2022,5902969.0981,TJ,M\n",
        encoding="utf-8",
    )
    report = ingest(path, con)[0]
    assert report.rows_stored == 1
    row = con.execute("""
        SELECT value_tj, unit_status FROM web
        WHERE country = 'FRA' AND year = 2022 AND flow = 'TFC'
        """).fetchone()
    assert row[1] == "tj_unchecked"
    assert row[0] == pytest.approx(5902969.0981)
    flag = con.execute("""
        SELECT flag FROM web_raw
        WHERE country = 'FRA' AND year = 2022 AND flow = 'TFC'
        """).fetchone()
    assert flag[0] == "M"
