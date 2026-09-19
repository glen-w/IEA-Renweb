from __future__ import annotations

from renweb.ingest.txt import format_fixed_width, parse_line
from renweb.refdata.codes import canon
from renweb.refdata.countries import to_iso3


def test_crosswalk_and_countries() -> None:
    assert canon("AGRICULT") == "AGRI_FOREST"
    assert canon("NONENUSE") == "NE_TOT"
    assert canon("MRENEW") == "RENEWABLES_TOTAL"
    assert canon("TFC") == "TFC"
    assert to_iso3("FRANCE") == "FRA"
    assert to_iso3("WORLD") == "WLD"
    assert to_iso3("AUSTRALI") == "AUS"
    assert to_iso3("AUSTRALIA") == "AUS"
    assert to_iso3("EU27") == "EU27_2020"


def test_each_line_is_its_own_record() -> None:
    lines = [
        format_fixed_width("FRANCE", "TOTAL", 2022, "TFC", "KTOE", 140989.9947),
        format_fixed_width("FRANCE", "TOTAL", 2022, "TFC", "TJ", 5902969.0981),
    ]
    parsed = [parse_line(line) for line in lines]
    assert all(item is not None for item in parsed)
    assert parsed[0]["unit"] == "KTOE"
    assert parsed[1]["unit"] == "TJ"
    assert parsed[0]["flow_raw"] == "TFC"
    assert parsed[1]["value"] == pytest_approx(5902969.0981)


def pytest_approx(value: float):
    import pytest

    return pytest.approx(value)


def test_missing_markers() -> None:
    for marker in ("..", "x", "c"):
        parsed = parse_line(
            format_fixed_width("FRANCE", "TOTAL", 2022, "TFC", "TJ", marker)
        )
        assert parsed is not None
        assert parsed["value"] is None


def test_real_layout_line() -> None:
    line = "FRANCE          TOTAL           2022            TFC             TJ                      5902969.0981 "
    assert len(line) == 101
    parsed = parse_line(line)
    assert parsed is not None
    assert parsed["iea_country"] == "FRANCE"
    assert parsed["product_raw"] == "TOTAL"
    assert parsed["year"] == 2022
    assert parsed["flow_raw"] == "TFC"
    assert parsed["unit"] == "TJ"
    assert parsed["value"] == pytest_approx(5902969.0981)
