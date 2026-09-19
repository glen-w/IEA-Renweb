"""Opt-in check against a local IEA extract. Never runs in CI."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from renweb.ingest.pipeline import ingest
from renweb.refdata.codes import canon

pytestmark = pytest.mark.skipif(
    not os.environ.get("RENWEB_IEA_DIR"),
    reason="Set RENWEB_IEA_DIR to a directory with your own World Energy Balances extract",
)


def test_france_2022_total_final_consumption(con) -> None:
    reports = ingest(Path(os.environ["RENWEB_IEA_DIR"]), con)
    assert any(
        not report.skipped_existing or report.rows_stored >= 0 for report in reports
    )
    row = con.execute(
        """
        SELECT value_tj, unit_status FROM web
        WHERE country = 'FRA' AND flow = ? AND product = ? AND year = 2022
        """,
        [canon("TFC"), canon("TOTAL")],
    ).fetchone()
    assert row is not None, "France 2022 TFC was not in the extract"
    assert row[1] in {"tj_checked", "tj_unchecked"}
    assert row[0] == pytest.approx(5_902_969.0981, rel=1e-4)
