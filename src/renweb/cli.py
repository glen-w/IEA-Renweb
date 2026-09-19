"""Command line for ingest, compute, validate, and export."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from renweb import __version__
from renweb.compute.dag import compute
from renweb.export.writers import ExportError, export_results
from renweb.ingest.irena import ingest_irena
from renweb.ingest.pipeline import IngestError, ingest
from renweb.ingest.worldbank import ingest_worldbank
from renweb.validate.checks import validate
from renweb.warehouse import connect

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Turn IEA World Energy Balances into renewable energy statistics.",
)
console = Console()


def _version(value: bool) -> None:
    if value:
        console.print(__version__)
        raise typer.Exit()


@app.callback()
def _callback(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version,
        is_eager=True,
        help="Print the version.",
    ),
) -> None:
    """Balances in, renewable statistics out."""


@app.command("ingest")
def ingest_cmd(
    path: Path = typer.Argument(..., help="A balances file or a directory of them."),
) -> None:
    """Load a fixed-width TXT, SDMX CSV, or zip extract into the warehouse."""
    con = connect()
    try:
        reports = ingest(path, con)
    except IngestError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    table = Table(title="Ingest")
    for column in (
        "file",
        "rows",
        "stored",
        "nulls",
        "duplicates",
        "unmapped",
        "status",
    ):
        table.add_column(column)
    for report in reports:
        table.add_row(
            report.filename,
            str(report.rows_read),
            str(report.rows_stored),
            str(report.null_values),
            str(report.duplicates_dropped),
            str(report.unmapped_countries),
            "already loaded" if report.skipped_existing else report.format,
        )
    console.print(table)
    summary = con.execute(
        "SELECT unit_status, count(*) FROM web GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall()
    if summary:
        console.print(
            "Unit check: " + ", ".join(f"{status} {count}" for status, count in summary)
        )


@app.command("ingest-worldbank")
def ingest_worldbank_cmd(
    start_year: int | None = typer.Option(None, "--start-year", help="First year."),
    end_year: int | None = typer.Option(None, "--end-year", help="Last year."),
) -> None:
    """Fetch World Bank population, GDP, and income into the warehouse."""
    con = connect()
    try:
        report = ingest_worldbank(con, start_year=start_year, end_year=end_year)
    except IngestError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(
        f"World Bank: {report.indicators} indicator rows, "
        f"{report.income_rows} income rows. "
        f"Attached {report.attached} optional result row(s)."
    )


@app.command("ingest-irena")
def ingest_irena_cmd(
    path: Path | None = typer.Argument(
        None,
        help="Optional capacity CSV. Default: fetch IRENASTAT.",
    ),
) -> None:
    """Load IRENA electricity capacity into the warehouse."""
    con = connect()
    try:
        report = ingest_irena(con, path)
    except IngestError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    source = report.table or (path.name if path is not None else "IRENASTAT")
    console.print(
        f"IRENA: {report.rows} capacity rows from {source}. "
        f"Attached {report.attached} optional result row(s)."
    )


@app.command("compute")
def compute_cmd(
    country: list[str] | None = typer.Option(
        None, "--country", help="ISO3 or aggregate code. Repeatable. Default: all."
    ),
    year: list[int] | None = typer.Option(
        None, "--year", help="Year. Repeatable. Default: all."
    ),
) -> None:
    """Calculate renewable statistics for the loaded balances."""
    con = connect()
    done = compute(con, countries=country, years=year)
    if done == 0:
        console.print("Nothing to compute. Load a balances extract first.")
        raise typer.Exit(code=1)
    console.print(f"Computed {done} country-year(s).")


@app.command("validate")
def validate_cmd() -> None:
    """Check identities, share bounds, and year-on-year jumps."""
    con = connect()
    findings = validate(con)
    if not findings:
        console.print("No findings.")
        return
    table = Table(title="Validation")
    for column in ("severity", "check", "country", "year", "message"):
        table.add_column(column)
    errors = 0
    for finding in findings:
        if finding.severity == "error":
            errors += 1
        table.add_row(
            finding.severity,
            finding.check,
            finding.country or "",
            "" if finding.year is None else str(finding.year),
            finding.message,
        )
    console.print(table)
    if errors:
        raise typer.Exit(code=1)


@app.command("export")
def export_cmd(
    dest: Path = typer.Argument(..., help="Directory to write into."),
    format: list[str] = typer.Option(
        ["parquet", "csv"], "--format", help="parquet, csv, or xlsx. Repeatable."
    ),
) -> None:
    """Write the results table."""
    con = connect()
    try:
        written = export_results(con, dest, format)
    except ExportError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    for path in written:
        console.print(str(path))


def main() -> None:
    app(prog_name="renweb")
