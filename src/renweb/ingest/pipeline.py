"""Load a World Energy Balances extract into the warehouse."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from renweb.ingest.txt import iter_text_lines, parse_line
from renweb.refdata.codes import canon, crosswalk
from renweb.refdata.countries import iea_to_iso3, to_iso3

logger = logging.getLogger(__name__)

CHUNK = 200_000

ARROW_SCHEMA = pa.schema(
    [
        ("source_id", pa.string()),
        ("iea_country", pa.string()),
        ("country", pa.string()),
        ("mapped", pa.bool_()),
        ("product", pa.string()),
        ("product_raw", pa.string()),
        ("flow", pa.string()),
        ("flow_raw", pa.string()),
        ("year", pa.int32()),
        ("unit", pa.string()),
        ("value", pa.float64()),
        ("flag", pa.string()),
    ]
)


class IngestError(ValueError):
    """The extract is missing, empty, or not a balances file this loader knows."""


@dataclass
class IngestReport:
    filename: str
    sha256: str
    format: str
    rows_read: int
    rows_stored: int
    null_values: int
    duplicates_dropped: int
    unmapped_countries: int
    skipped_existing: bool


def ingest(
    path: str | Path,
    con: Any,
    on_progress: Callable[[int], None] | None = None,
) -> list[IngestReport]:
    """Load a file or every balances file in a directory.

    Accepts fixed-width ``.txt``, SDMX ``.csv``, and ``.zip`` archives of the
    fixed-width files. The same content (sha256) is not loaded twice. A file
    whose name is already loaded but whose bytes changed replaces the old rows.
    """
    target = Path(path).expanduser()
    if not target.exists():
        raise IngestError(f"No such file: {target}")
    if target.is_dir():
        files = _files_in(target)
        if not files:
            raise IngestError(f"No balances files in {target}")
        return [report for file in files for report in ingest(file, con, on_progress)]
    kind = _sniff(target)
    if kind == "zip":
        return _ingest_zip(target, con, on_progress)
    if kind == "csv":
        return [_ingest_csv(target, con)]
    return [_ingest_txt_file(target, con, on_progress)]


def _files_in(directory: Path) -> list[Path]:
    found: list[Path] = []
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in {".zip", ".csv", ".txt"} or path.name.upper().startswith(
            "WORLDBIG"
        ):
            found.append(path)
    return found


def _sniff(path: Path) -> str:
    if path.suffix.lower() == ".zip":
        return "zip"
    if path.suffix.lower() == ".csv":
        return "csv"
    with path.open("rb") as handle:
        start = handle.read(4096)
    if b"ENERGY_BALANCE_FLOW" in start or b"OBS_VALUE" in start:
        return "csv"
    return "txt"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _claim(con: Any, filename: str, sha: str) -> str:
    """Return skip, or delete a stale filename and return insert."""
    existing = con.execute(
        "SELECT filename FROM source WHERE sha256 = ?", [sha]
    ).fetchone()
    if existing:
        return "skip"
    stale = con.execute(
        "SELECT sha256 FROM source WHERE filename = ?", [filename]
    ).fetchone()
    if stale:
        con.execute("DELETE FROM web_raw WHERE source_id = ?", [stale[0]])
        con.execute("DELETE FROM source WHERE sha256 = ?", [stale[0]])
    return "insert"


def _record(con: Any, report: IngestReport) -> None:
    con.execute(
        """
        INSERT INTO source VALUES (?, ?, ?, ?, ?, ?, current_timestamp)
        """,
        [
            report.sha256,
            report.filename,
            report.format,
            report.rows_stored,
            report.null_values,
            report.unmapped_countries,
        ],
    )


def _commit_stage(con: Any, report_name: str) -> tuple[int, int, int, int]:
    stage_count = con.execute("SELECT count(*) FROM ingest_stage").fetchone()[0]
    nulls = con.execute(
        "SELECT count(*) FROM ingest_stage WHERE value IS NULL"
    ).fetchone()[0]
    unmapped = con.execute(
        "SELECT count(DISTINCT iea_country) FROM ingest_stage WHERE NOT mapped"
    ).fetchone()[0]
    before = con.execute("SELECT count(*) FROM web_raw").fetchone()[0]
    con.execute("""
        INSERT INTO web_raw
        SELECT
            source_id,
            iea_country,
            any_value(country),
            any_value(mapped),
            product,
            any_value(product_raw),
            flow,
            any_value(flow_raw),
            year,
            unit,
            max(value),
            any_value(flag)
        FROM ingest_stage
        GROUP BY source_id, iea_country, product, flow, year, unit
        """)
    after = con.execute("SELECT count(*) FROM web_raw").fetchone()[0]
    stored = int(after - before)
    dropped = int(stage_count - stored)
    if dropped:
        logger.info("%s: dropped %s duplicate rows", report_name, dropped)
    con.execute("DROP TABLE IF EXISTS ingest_stage")
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_web_raw_country_year ON web_raw(country, year)"
    )
    return int(stage_count), stored, int(nulls), int(unmapped)


def _ingest_txt_file(
    path: Path,
    con: Any,
    on_progress: Callable[[int], None] | None,
    filename: str | None = None,
    lines: Iterator[str] | None = None,
    sha: str | None = None,
) -> IngestReport:
    label = filename or path.name
    digest = sha if sha is not None else _sha256(path)
    if _claim(con, label, digest) == "skip":
        logger.info("%s already loaded (%s)", label, digest[:12])
        return IngestReport(label, digest, "txt", 0, 0, 0, 0, 0, True)
    if lines is None:
        _, lines = next(iter_text_lines(path))
    db_row = con.execute("PRAGMA database_list").fetchone()
    warehouse = Path(db_row[2]).parent if db_row and db_row[2] else path.parent
    tmp = warehouse / f".renweb-{digest[:12]}.parquet"
    writer: pq.ParquetWriter | None = None
    batch: list[dict] = []
    read = 0

    def flush() -> None:
        nonlocal writer
        if not batch:
            return
        table = pa.Table.from_pylist(batch, schema=ARROW_SCHEMA)
        if writer is None:
            writer = pq.ParquetWriter(tmp, ARROW_SCHEMA)
        writer.write_table(table)
        batch.clear()

    try:
        for line in lines:
            parsed = parse_line(line)
            if parsed is None:
                continue
            read += 1
            iso = to_iso3(parsed["iea_country"])
            batch.append(
                {
                    "source_id": digest,
                    "iea_country": parsed["iea_country"],
                    "country": iso or canon(parsed["iea_country"]),
                    "mapped": iso is not None,
                    "product": canon(parsed["product_raw"]),
                    "product_raw": parsed["product_raw"],
                    "flow": canon(parsed["flow_raw"]),
                    "flow_raw": parsed["flow_raw"],
                    "year": parsed["year"],
                    "unit": parsed["unit"],
                    "value": parsed["value"],
                    "flag": parsed["flag"],
                }
            )
            if len(batch) >= CHUNK:
                flush()
                if on_progress:
                    on_progress(read)
        flush()
        if writer is not None:
            writer.close()
            writer = None
        if read == 0:
            raise IngestError(f"{label} has no balances records")
        con.execute(
            "CREATE TEMP TABLE ingest_stage AS SELECT * FROM read_parquet(?)",
            [str(tmp)],
        )
        _stage_count, stored, nulls, unmapped = _commit_stage(con, label)
        report = IngestReport(
            filename=label,
            sha256=digest,
            format="txt",
            rows_read=read,
            rows_stored=stored,
            null_values=nulls,
            duplicates_dropped=read - stored,
            unmapped_countries=unmapped,
            skipped_existing=False,
        )
        _record(con, report)
        logger.info("loaded %s: %s rows", label, stored)
        return report
    finally:
        if writer is not None:
            writer.close()
        if tmp.exists():
            tmp.unlink()


def _ingest_zip(
    path: Path, con: Any, on_progress: Callable[[int], None] | None
) -> list[IngestReport]:
    reports: list[IngestReport] = []
    for label, lines in iter_text_lines(path):
        # Hash the member by re-reading it. iter_text_lines already opened it,
        # so hash from the lines we would otherwise parse twice. Compute the
        # digest from a fresh open to keep skip-detection correct.
        import zipfile

        digest = hashlib.sha256()
        with (
            zipfile.ZipFile(path) as archive,
            archive.open(_member_name(archive, label)) as handle,
        ):
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        sha = digest.hexdigest()
        filename = f"{path.name}:{label}"
        if _claim(con, filename, sha) == "skip":
            reports.append(IngestReport(filename, sha, "txt", 0, 0, 0, 0, 0, True))
            # Drain the already-open iterator so the zip handle can close.
            for _ in lines:
                pass
            continue
        reports.append(
            _ingest_txt_file(
                path,
                con,
                on_progress,
                filename=filename,
                lines=lines,
                sha=sha,
            )
        )
    if not reports:
        raise IngestError(f"{path} contains no .txt members")
    return reports


def _member_name(archive: Any, label: str) -> str:
    for name in archive.namelist():
        if Path(name).name == label:
            return name
    raise IngestError(f"Missing zip member {label}")


def _ingest_csv(path: Path, con: Any) -> IngestReport:
    digest = _sha256(path)
    if _claim(con, path.name, digest) == "skip":
        return IngestReport(path.name, digest, "csv", 0, 0, 0, 0, 0, True)
    _register_maps(con)
    con.execute(
        """
        CREATE TEMP TABLE sdmx AS
        SELECT * FROM read_csv(?, header = true, auto_detect = true, ignore_errors = true)
        """,
        [str(path)],
    )
    columns = {
        row[0].lower(): row[0] for row in con.execute("DESCRIBE sdmx").fetchall()
    }

    def pick(*options: str) -> str:
        for option in options:
            if option.lower() in columns:
                return _quote(columns[option.lower()])
        raise IngestError(
            f"{path.name} is missing a column. Looked for {', '.join(options)}. "
            f"Found {', '.join(columns)}."
        )

    country = pick("COUNTRY", "Country")
    flow = pick("ENERGY_BALANCE_FLOW", "FLOW", "CODE_FLOW")
    product = pick("ENERGY_PRODUCT", "PRODUCT", "CODE_PRODUCT")
    year = pick("TIME_PERIOD", "YEAR", "TIME")
    value = pick("OBS_VALUE", "VALUE", "Observation value")
    unit = pick("UNIT", "Unit", "MEASURE")
    flag = None
    for option in ("QUALIFIER", "CONF_STATUS", "Flag Codes", "FLAG"):
        if option.lower() in columns:
            flag = _quote(columns[option.lower()])
            break
    flag_sql = f"nullif(trim(cast({flag} AS VARCHAR)), '')" if flag else "NULL"
    con.execute(
        f"""
        CREATE TEMP TABLE ingest_stage AS
        SELECT
            ? AS source_id,
            upper(trim(cast({country} AS VARCHAR))) AS iea_country,
            coalesce(
                cm.iso3,
                cx.new,
                upper(trim(cast({country} AS VARCHAR)))
            ) AS country,
            cm.iso3 IS NOT NULL AS mapped,
            coalesce(px.new, upper(trim(cast({product} AS VARCHAR)))) AS product,
            upper(trim(cast({product} AS VARCHAR))) AS product_raw,
            coalesce(fx.new, upper(trim(cast({flow} AS VARCHAR)))) AS flow,
            upper(trim(cast({flow} AS VARCHAR))) AS flow_raw,
            try_cast({year} AS INTEGER) AS year,
            CASE upper(replace(trim(cast({unit} AS VARCHAR)), ' ', ''))
                WHEN 'TJ' THEN 'TJ'
                WHEN 'TJ_BAL' THEN 'TJ'
                WHEN 'KTOE' THEN 'KTOE'
                WHEN 'GWH' THEN 'GWH'
                WHEN 'GWH_BAL' THEN 'GWH'
                ELSE NULL
            END AS unit,
            try_cast({value} AS DOUBLE) AS value,
            {flag_sql} AS flag
        FROM sdmx
        LEFT JOIN country_map cm
            ON cm.iea_code = upper(trim(cast({country} AS VARCHAR)))
        LEFT JOIN code_map cx
            ON cx.old = upper(trim(cast({country} AS VARCHAR)))
        LEFT JOIN code_map px
            ON px.old = upper(trim(cast({product} AS VARCHAR)))
        LEFT JOIN code_map fx
            ON fx.old = upper(trim(cast({flow} AS VARCHAR)))
        WHERE try_cast({year} AS INTEGER) IS NOT NULL
          AND CASE upper(replace(trim(cast({unit} AS VARCHAR)), ' ', ''))
                WHEN 'TJ' THEN 'TJ'
                WHEN 'TJ_BAL' THEN 'TJ'
                WHEN 'KTOE' THEN 'KTOE'
                WHEN 'GWH' THEN 'GWH'
                WHEN 'GWH_BAL' THEN 'GWH'
                ELSE NULL
              END IS NOT NULL
        """,
        [digest],
    )
    con.execute("DROP TABLE IF EXISTS sdmx")
    read = con.execute("SELECT count(*) FROM ingest_stage").fetchone()[0]
    if read == 0:
        con.execute("DROP TABLE IF EXISTS ingest_stage")
        raise IngestError(f"{path.name} has no balances rows")
    _stage_count, stored, nulls, unmapped = _commit_stage(con, path.name)
    report = IngestReport(
        filename=path.name,
        sha256=digest,
        format="csv",
        rows_read=int(read),
        rows_stored=stored,
        null_values=nulls,
        duplicates_dropped=int(read - stored),
        unmapped_countries=unmapped,
        skipped_existing=False,
    )
    _record(con, report)
    _drop_maps(con)
    return report


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _register_maps(con: Any) -> None:
    _drop_maps(con)
    con.execute("CREATE TEMP TABLE country_map (iea_code VARCHAR, iso3 VARCHAR)")
    con.executemany(
        "INSERT INTO country_map VALUES (?, ?)",
        list(iea_to_iso3().items()),
    )
    con.execute("CREATE TEMP TABLE code_map (old VARCHAR, new VARCHAR)")
    con.executemany(
        "INSERT INTO code_map VALUES (?, ?)",
        list(crosswalk().items()),
    )


def _drop_maps(con: Any) -> None:
    con.execute("DROP TABLE IF EXISTS country_map")
    con.execute("DROP TABLE IF EXISTS code_map")
