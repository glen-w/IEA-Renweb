"""Synthetic World Energy Balances demo extract (not IEA data)."""

from __future__ import annotations

from renweb.compute.formulas import Frame, compute_one
from renweb.ingest.txt import format_fixed_width
from renweb.refdata.codes import KTOE_TO_TJ

# Structural template shared with tests/test_formulas.py::_sample.
BASE_TJ: dict[tuple[str, str], float] = {
    ("TFC", "TOTAL"): 1000,
    ("NONENUSE", "TOTAL"): 100,
    ("TFC", "MRENEW"): 400,
    ("TFC", "ELECTR"): 200,
    ("TFC", "HEAT"): 50,
    ("ELOUTPUT", "TOTAL"): 100,
    ("ELOUTPUT", "MRENEW"): 40,
    ("ELOUTPUT", "HYDRO"): 30,
    ("ELOUTPUT", "NUCLEAR"): 10,
    ("ELOUTPUT", "WIND"): 10,
    ("HEATOUT", "TOTAL"): 20,
    ("HEATOUT", "MRENEW"): 10,
    ("RESIDENT", "TOTAL"): 300,
    ("RESIDENT", "PRIMSBIO"): 80,
    ("RESIDENT", "CHARCOAL"): 20,
    ("RESIDENT", "ELECTR"): 50,
    ("RESIDENT", "MRENEW"): 120,
    ("RESIDENT", "SOLARTH"): 10,
    ("RESIDENT", "GEOTHERM"): 5,
    ("RESIDENT", "HEAT"): 15,
    ("COMMPUB", "TOTAL"): 100,
    ("COMMPUB", "MRENEW"): 10,
    ("TOTIND", "TOTAL"): 250,
    ("TOTIND", "ELECTR"): 80,
    ("TOTIND", "MRENEW"): 40,
    ("TOTIND", "SOLARTH"): 5,
    ("TOTIND", "GEOTHERM"): 5,
    ("TOTIND", "HEAT"): 20,
    ("TOTTRANS", "TOTAL"): 200,
    ("TOTTRANS", "ELECTR"): 30,
    ("TOTTRANS", "BIODIESEL"): 25,
    ("AGRICULT", "TOTAL"): 40,
    ("FISHING", "TOTAL"): 10,
    ("TES", "TOTAL"): 1500,
    ("IMPORTS", "NATGAS"): 100,
    ("IMPORTS", "ELECTR"): 100,
    ("LOSSES", "ELECTR"): 10,
    ("PUMPSTOR", "ELECTR"): 5,
}

# IEA bulk-file country label -> (ISO3, scale on BASE_TJ).
COUNTRIES: dict[str, tuple[str, float]] = {
    "EASTFENIA": ("EFN", 1.0),
    "WESTMARSH": ("WMS", 1.41),
    "NORTHALIA": ("NTH", 0.87),
    "SOUTHAVIA": ("STH", 2.05),
    "NIGERIA": ("NGA", 6120.0),
    "FRANCE": ("FRA", 5902.969),
}

YEARS = range(1960, 2024)


def _lines_for_country_year(country: str, scale: float, year: int) -> list[str]:
    drift = 1.0 + 0.012 * (year - 2020)
    lines: list[str] = []
    for (flow, product), base in BASE_TJ.items():
        tj = base * scale * drift
        if flow == "ELOUTPUT":
            gwh = tj / 3.6
            lines.append(format_fixed_width(country, product, year, flow, "TJ", gwh))
            lines.append(format_fixed_width(country, product, year, flow, "KTOE", gwh))
        else:
            lines.append(format_fixed_width(country, product, year, flow, "TJ", tj))
            lines.append(
                format_fixed_width(
                    country, product, year, flow, "KTOE", tj / KTOE_TO_TJ
                )
            )
    return lines


def build_lines() -> list[str]:
    out: list[str] = []
    for country, (_iso, scale) in COUNTRIES.items():
        for year in YEARS:
            out.extend(_lines_for_country_year(country, scale, year))
    return out


def golden_nga_2022() -> dict[str, float]:
    drift = 1.0 + 0.012 * (2022 - 2020)
    pairs = {key: value * 6120.0 * drift for key, value in BASE_TJ.items()}
    return {
        name: value
        for name, (value, _unit) in compute_one(
            Frame.from_pairs(pairs), "NGA", 2022
        ).items()
    }
