"""Fixed-width World Energy Balances records.

Each record is one 101-character line:

    country (16) product (16) year (16) flow (16) unit (16) value (21)

The value field is right aligned and may be a number, ``..`` (missing),
``x`` (not applicable), or ``c`` (confidential).
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from pathlib import Path

FIELD = 16
LINE_LEN = 101
MISSING = {"", "..", "...", "x", "X", "c", "C", "-"}
UNITS = {"TJ": "TJ", "KTOE": "KTOE", "GWH": "GWH", "TJ_BAL": "TJ", "GWH_BAL": "GWH"}


def format_fixed_width(
    country: str,
    product: str,
    year: int | str,
    flow: str,
    unit: str,
    value: float | str,
) -> str:
    """Build one bulk-file line. Used by tests and by anyone writing fixtures."""

    def cell(text: str) -> str:
        if len(text) > FIELD:
            raise ValueError(f"{text!r} is longer than {FIELD} characters")
        return text.ljust(FIELD)

    if isinstance(value, str):
        rendered = value
    else:
        rendered = f"{value:.10f}".rstrip("0").rstrip(".")
        if rendered in {"", "-0", "-"}:
            rendered = "0"
    if len(rendered) > 20:
        rendered = f"{float(value):.6g}"
    line = (
        cell(str(country))
        + cell(str(product))
        + cell(str(year))
        + cell(str(flow))
        + cell(str(unit))
        + rendered.rjust(20)
        + " "
    )
    if len(line) != LINE_LEN:
        raise ValueError(f"line length {len(line)} != {LINE_LEN}")
    return line


def parse_value(field: str) -> tuple[float | None, str | None]:
    token = field.strip()
    if token in MISSING:
        return None, None
    flag = None
    if len(token) > 1 and token[-1].isalpha() and token[-1] not in "eE":
        flag = token[-1]
        token = token[:-1].strip()
        if token in MISSING:
            return None, flag
    try:
        return float(token), flag
    except ValueError:
        return None, flag


def parse_line(line: str) -> dict | None:
    """Parse one record. Returns None for blanks and short lines.

    Consecutive lines are independent. A ktoe row followed by a TJ row is
    two records, not one.
    """
    text = line.rstrip("\r\n")
    if len(text) < 80 or not text.strip():
        return None
    country = text[0:16].strip()
    product = text[16:32].strip()
    year_text = text[32:48].strip()
    flow = text[48:64].strip()
    raw_unit = text[64:80].strip().upper().replace(" ", "")
    if not country or not year_text.isdigit() or len(year_text) != 4:
        return None
    unit = UNITS.get(raw_unit)
    if unit is None or not product or not flow:
        return None
    value, flag = parse_value(text[80:] if len(text) > 80 else "")
    return {
        "iea_country": country,
        "product_raw": product,
        "flow_raw": flow,
        "year": int(year_text),
        "unit": unit,
        "value": value,
        "flag": flag,
    }


def iter_text_lines(path: Path) -> Iterator[tuple[str, Iterator[str]]]:
    """Yield ``(label, lines)`` for a txt file or a zip of txt members."""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = [
                name
                for name in archive.namelist()
                if name.lower().endswith(".txt") and not name.endswith("/")
            ]
            if not names:
                raise ValueError(f"{path} contains no .txt members")
            for name in names:
                with archive.open(name) as handle:

                    def member_lines(handle=handle):
                        for raw in handle:
                            yield raw.decode("latin-1")

                    yield Path(name).name, member_lines()
        return

    def file_lines() -> Iterator[str]:
        with path.open("r", encoding="latin-1", newline="") as handle:
            yield from handle

    yield path.name, file_lines()
