"""IEA code crosswalk and physical conversion constants."""

from __future__ import annotations

import csv
import json
from functools import cache
from pathlib import Path

# IEA definition: 1 toe = 41.868 GJ, so 1 ktoe = 41.868 TJ.
KTOE_TO_TJ = 41.868
GWH_TO_TJ = 3.6
UNIT_TOLERANCE = 0.02

# Legacy own-use conversion offsets. The multiplier is 1 minus
# (offset + category share + loss share). See docs/METHODOLOGY.md.
CONV_HYDRO = -0.01
CONV_NUCLEAR_GEO_CSP = -0.06
CONV_OTHER_THERMAL = -0.07


def read_text(name: str) -> str:
    path = Path(__file__).resolve().parent / "data" / name
    return path.read_text(encoding="utf-8-sig")


@cache
def crosswalk() -> dict[str, str]:
    table: dict[str, str] = {}
    rows = csv.DictReader(read_text("code_crosswalk.csv").splitlines())
    for row in rows:
        old = (row.get("old") or "").strip()
        new = (row.get("new") or "").strip()
        if old and new:
            table[old] = new
    return table


def canon(code: str) -> str:
    """Map a legacy balance code onto the current code. Unknown codes pass through."""
    key = code.strip()
    table = crosswalk()
    return table.get(key, table.get(key.upper(), key))


@cache
def fossil_products() -> tuple[str, ...]:
    raw = json.loads(read_text("fossil_fuels.json"))
    seen: list[str] = []
    for code in raw:
        mapped = canon(str(code))
        if mapped not in seen:
            seen.append(mapped)
    return tuple(seen)


@cache
def fallback_multipliers() -> dict[str, float]:
    raw = json.loads(read_text("adjustment_factors.json"))
    return {str(key): float(value) for key, value in raw.items()}
