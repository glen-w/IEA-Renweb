"""End-to-end check on the committed synthetic balances example."""

from __future__ import annotations

from pathlib import Path

import pytest

from renweb.compute.dag import compute
from renweb.demo_balances import COUNTRIES, YEARS, golden_nga_2022
from renweb.ingest.pipeline import ingest
from renweb.validate.checks import validate

EXAMPLE_ZIP = Path(__file__).resolve().parents[1] / "examples" / "worldbalances_demo.zip"


def test_example_zip_exists() -> None:
    assert EXAMPLE_ZIP.is_file(), "Run examples/generate_demo_extract.py to create the demo zip"


def test_example_ingest_compute_validate(con) -> None:
    expected = golden_nga_2022()
    reports = ingest(EXAMPLE_ZIP, con)
    assert reports and reports[0].rows_stored > 0
    assert reports[0].unmapped_countries == 0

    count = compute(con)
    assert count == len(COUNTRIES) * len(YEARS)

    errors = [item for item in validate(con) if item.severity == "error"]
    assert not errors

    row = con.execute(
        """
        SELECT value FROM results
        WHERE country = 'NGA' AND year = 2022 AND variable = 'economy_share_renewable'
        """
    ).fetchone()
    assert row is not None
    assert row[0] == pytest.approx(expected["economy_share_renewable"])

    fictional = con.execute(
        "SELECT COUNT(DISTINCT year) FROM results WHERE country = 'EFN'"
    ).fetchone()
    assert fictional[0] == len(YEARS)
