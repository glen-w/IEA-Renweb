"""Methodological assumption tables that the IEA balances do not publish."""

from __future__ import annotations

import json
from functools import cache

from renweb.refdata.codes import read_text
from renweb.refdata.countries import heat_regions

DEFAULT_ELEC_FOR_HEAT = {"industry": 0.04, "buildings": 0.11, "agriculture": 0.04}
DEFAULT_BIOENERGY_SHARE = 0.10


@cache
def _heat_rows() -> tuple[dict, ...]:
    return tuple(json.loads(read_text("heat_shares.json")))


@cache
def _bio_rows() -> tuple[dict, ...]:
    return tuple(json.loads(read_text("bioenergy_shares.json")))


def _region_names(country: str) -> list[str]:
    code = country.strip().upper()
    matches = [name for name, members in heat_regions().items() if code in members]
    matches.sort(key=lambda name: len(heat_regions()[name]))
    return matches


def elec_for_heat_share(country: str, sector: str, year: int) -> float:
    """Share of sector heat demand that is met by electricity.

    ``sector`` is ``industry``, ``buildings``, or ``agriculture``. Agriculture
    uses the industry figure when it has no row of its own. Real (not forecast)
    rows are preferred, then the latest year at or before ``year``.
    """
    sector_key = "industry" if sector == "agriculture" else sector
    rows = [
        row
        for row in _heat_rows()
        if row.get("type") == "real" and row.get("sector") == sector_key
    ]
    country_code = country.strip().upper()
    region_names = set(_region_names(country_code))

    def pick(candidates: list[dict]) -> float | None:
        eligible = [row for row in candidates if int(row["year"]) <= year]
        pool = eligible or candidates
        if not pool:
            return None
        chosen = max(pool, key=lambda row: int(row["year"]))
        return float(chosen["share"])

    by_country = [
        row for row in rows if str(row.get("area", "")).upper() == country_code
    ]
    found = pick(by_country)
    if found is not None:
        return found
    by_region = [row for row in rows if row.get("area") in region_names]
    found = pick(by_region)
    if found is not None:
        return found
    world = [row for row in rows if row.get("area") == "World"]
    found = pick(world)
    if found is not None:
        return found
    return DEFAULT_ELEC_FOR_HEAT.get(sector_key, 0.04)


def bioenergy_share(country: str) -> float:
    """Country or regional solid-bioenergy assumption, else 0.10."""
    code = country.strip().upper()
    rows = list(_bio_rows())
    for row in rows:
        if (
            row.get("area_type") == "country"
            and str(row.get("area", "")).upper() == code
        ):
            return float(row["value"])
    regions = set(_region_names(code))
    regional = [
        row
        for row in rows
        if row.get("area_type") == "region" and row.get("area") in regions
    ]
    if regional:
        regional.sort(key=lambda row: len(heat_regions().get(str(row["area"]), ())))
        return float(regional[0]["value"])
    return DEFAULT_BIOENERGY_SHARE
