# Agent notes

Library and CLI that load an IEA World Energy Balances extract into DuckDB and calculate renewable energy statistics. Start from [README.md](README.md) and [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

The warehouse lives at `RENWEB_DATA` or `~/Documents/renweb_data/renweb.duckdb`. Do not commit it, and do not commit an IEA extract.

World Bank and IRENASTAT are optional extras (`worldbank`, `irena`). They add source tables and extra result variables. They must not change the IEA identities in `docs/METHODOLOGY.md`.

`notebooks/quicklook.py` (optional `notebook` extra) is a marimo quick look over the warehouse. It opens DuckDB read-only through `renweb.notebook.connect_read_only` and must not compute or write. Stop it before `ingest` or `compute`. Do not format `notebooks/` with Black or Ruff, and do not name a notebook `renweb.py`: marimo puts `notebooks/` on `sys.path` and it would shadow the package.

Shares are fractions. Energy results are terajoules. Do not apply a blanket "labelled TJ but actually PJ" correction: the bulk file's TJ column is terajoules, except electricity output, where it is gigawatt-hours. The check is in `renweb.warehouse.web_view_sql`.
