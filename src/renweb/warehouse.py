"""DuckDB warehouse for balances and calculated results."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import duckdb

from renweb.refdata.codes import GWH_TO_TJ, KTOE_TO_TJ, UNIT_TOLERANCE

SCHEMA = """
CREATE TABLE IF NOT EXISTS source (
    sha256 VARCHAR PRIMARY KEY,
    filename VARCHAR UNIQUE,
    format VARCHAR,
    row_count BIGINT,
    null_count BIGINT,
    unmapped_count BIGINT,
    ingested_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS web_raw (
    source_id VARCHAR,
    iea_country VARCHAR,
    country VARCHAR,
    mapped BOOLEAN,
    product VARCHAR,
    product_raw VARCHAR,
    flow VARCHAR,
    flow_raw VARCHAR,
    year INTEGER,
    unit VARCHAR,
    value DOUBLE,
    flag VARCHAR
);

CREATE TABLE IF NOT EXISTS results (
    country VARCHAR,
    year INTEGER,
    variable VARCHAR,
    value DOUBLE,
    unit VARCHAR,
    method_version VARCHAR
);

CREATE TABLE IF NOT EXISTS wb_indicators (
    country VARCHAR,
    year INTEGER,
    indicator VARCHAR,
    value DOUBLE,
    unit VARCHAR,
    fetched_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS wb_income (
    country VARCHAR PRIMARY KEY,
    income_level_id VARCHAR,
    income_level VARCHAR,
    fetched_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS capacity (
    country VARCHAR,
    year INTEGER,
    technology VARCHAR,
    grid VARCHAR,
    capacity_mw DOUBLE
);
"""


def warehouse_path() -> Path:
    """Resolve the DuckDB file.

    ``RENWEB_DATA`` may be a ``.duckdb`` path or a directory. The default is
    ``~/Documents/renweb_data/renweb.duckdb``, outside the git tree.
    """
    raw = os.environ.get("RENWEB_DATA")
    if raw:
        path = Path(raw).expanduser()
        if path.suffix == ".duckdb":
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        path.mkdir(parents=True, exist_ok=True)
        return path / "renweb.duckdb"
    path = Path.home() / "Documents" / "renweb_data" / "renweb.duckdb"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def web_view_sql() -> str:
    tol = UNIT_TOLERANCE
    ktoe = KTOE_TO_TJ
    gwh = GWH_TO_TJ
    return f"""
    CREATE OR REPLACE VIEW web AS
    WITH paired AS (
        SELECT
            country,
            product,
            flow,
            year,
            max(CASE WHEN unit = 'TJ' THEN value END) AS tj,
            max(CASE WHEN unit = 'KTOE' THEN value END) AS ktoe,
            max(CASE WHEN unit = 'GWH' THEN value END) AS gwh
        FROM web_raw
        GROUP BY 1, 2, 3, 4
    )
    SELECT
        country,
        product,
        flow,
        year,
        CASE
            WHEN tj IS NOT NULL AND ktoe IS NOT NULL
                 AND abs(ktoe) <= 1e-9 AND abs(tj) <= 1e-9 THEN 0
            WHEN tj IS NOT NULL AND ktoe IS NOT NULL AND abs(ktoe) > 1e-6
                 AND abs(tj - ktoe) <= {tol} * greatest(abs(ktoe), 1.0)
                 AND abs(tj / ktoe - {ktoe}) > {tol} * {ktoe}
                THEN tj * {gwh}
            WHEN tj IS NOT NULL AND ktoe IS NOT NULL AND abs(ktoe) > 1e-6
                 AND abs(tj / ktoe - {ktoe}) <= {tol} * {ktoe}
                THEN tj
            WHEN tj IS NOT NULL AND ktoe IS NOT NULL THEN NULL
            WHEN tj IS NOT NULL THEN tj
            WHEN ktoe IS NOT NULL THEN ktoe * {ktoe}
            WHEN gwh IS NOT NULL THEN gwh * {gwh}
            ELSE NULL
        END AS value_tj,
        CASE
            WHEN tj IS NOT NULL AND ktoe IS NOT NULL
                 AND abs(ktoe) <= 1e-9 AND abs(tj) <= 1e-9 THEN 'tj_checked'
            WHEN tj IS NOT NULL AND ktoe IS NOT NULL AND abs(ktoe) > 1e-6
                 AND abs(tj - ktoe) <= {tol} * greatest(abs(ktoe), 1.0)
                 AND abs(tj / ktoe - {ktoe}) > {tol} * {ktoe}
                THEN 'electricity_output_gwh'
            WHEN tj IS NOT NULL AND ktoe IS NOT NULL AND abs(ktoe) > 1e-6
                 AND abs(tj / ktoe - {ktoe}) <= {tol} * {ktoe}
                THEN 'tj_checked'
            WHEN tj IS NOT NULL AND ktoe IS NOT NULL THEN 'suspect'
            WHEN tj IS NOT NULL THEN 'tj_unchecked'
            WHEN ktoe IS NOT NULL THEN 'from_ktoe'
            WHEN gwh IS NOT NULL THEN 'from_gwh'
            ELSE 'missing'
        END AS unit_status,
        tj AS raw_tj,
        ktoe AS raw_ktoe
    FROM paired
    """


def connect(path: Path | None = None) -> Any:
    db = path or warehouse_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db))
    con.execute(SCHEMA)
    con.execute(web_view_sql())
    return con
