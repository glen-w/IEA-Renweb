"""Unit checks for the synthetic demo extract builder."""

from __future__ import annotations

import pytest

from renweb.demo_balances import (
    BASE_TJ,
    COUNTRIES,
    YEARS,
    _lines_for_country_year,
    golden_nga_2022,
)
from renweb.ingest.txt import parse_line
from renweb.refdata.countries import to_iso3


def test_fictional_and_real_demo_countries_map() -> None:
    for label, (iso3, _scale) in COUNTRIES.items():
        assert to_iso3(label) == iso3


def test_lines_for_country_year_pair_units_and_eloutput() -> None:
    lines = _lines_for_country_year("EASTFENIA", 1.0, 2022)
    assert len(lines) == len(BASE_TJ) * 2
    assert all(len(line) == 101 for line in lines)

    by_key: dict[tuple[str, str, str], object] = {}
    for line in lines:
        record = parse_line(line)
        assert record is not None
        by_key[(record["flow_raw"], record["product_raw"], record["unit"])] = record[
            "value"
        ]

    tfc_tj = by_key[("TFC", "TOTAL", "TJ")]
    tfc_ktoe = by_key[("TFC", "TOTAL", "KTOE")]
    assert isinstance(tfc_tj, float) and isinstance(tfc_ktoe, float)
    assert tfc_tj == pytest.approx(tfc_ktoe * 41.868, rel=1e-9)

    hydro_tj = by_key[("ELOUTPUT", "HYDRO", "TJ")]
    hydro_ktoe = by_key[("ELOUTPUT", "HYDRO", "KTOE")]
    assert hydro_tj == hydro_ktoe


def test_golden_nga_2022_share_identity() -> None:
    golden = golden_nga_2022()
    total = (
        golden["economy_share_fossil"]
        + golden["economy_share_nuclear"]
        + golden["economy_share_renewable"]
    )
    assert total == pytest.approx(1.0, abs=1e-9)
    assert len(YEARS) == 2024 - 1960
