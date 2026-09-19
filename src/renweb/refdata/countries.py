"""IEA country codes, regions, and OECD membership."""

from __future__ import annotations

import csv
import json
from functools import cache

from renweb.refdata.codes import canon, read_text


@cache
def country_aliases() -> dict[str, str]:
    """Old bulk-file country code to the current SDMX country code."""
    table: dict[str, str] = {}
    rows = csv.DictReader(read_text("country_crosswalk.csv").splitlines())
    for row in rows:
        old = (row.get("old") or "").strip().upper()
        new = (row.get("new") or "").strip().upper()
        if old and new:
            table[old] = new
    return table


@cache
def iea_to_iso3() -> dict[str, str]:
    rows = json.loads(read_text("iea_codes.json"))
    table: dict[str, str] = {}
    for row in rows:
        iea = str(row["iea_code"]).strip().upper()
        iso = str(row["iso3_code"]).strip()
        table[iea] = iso
        table[canon(iea).upper()] = iso
    for old, new in country_aliases().items():
        if old in table and new not in table:
            table[new] = table[old]
        elif new in table and old not in table:
            table[old] = table[new]
    if "MPALESTINE" in table:
        table["PALESTINE"] = table["MPALESTINE"]
    if "EU27_2020" in table:
        table["EU27"] = table["EU27_2020"]
    return table


def to_iso3(code: str) -> str | None:
    key = code.strip().upper()
    table = iea_to_iso3()
    if key in table:
        return table[key]
    mapped = canon(key).upper()
    return table.get(mapped)


@cache
def oecd_members() -> frozenset[str]:
    rows = json.loads(read_text("oecd_members.json"))
    return frozenset(str(code).strip().upper() for code in rows)


def is_oecd(country: str) -> bool:
    return country.strip().upper() in oecd_members()


@cache
def iea_regions() -> dict[str, frozenset[str]]:
    raw = json.loads(read_text("iea_regions.json"))
    return {
        name: frozenset(str(code).upper() for code in members)
        for name, members in raw.items()
    }
