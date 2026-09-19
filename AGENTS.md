# Agent notes

Library and CLI that load an IEA World Energy Balances extract into DuckDB and calculate renewable energy statistics. Start from [README.md](README.md) and [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

The warehouse lives at `RENWEB_DATA` or `~/Documents/renweb_data/renweb.duckdb`. Do not commit it, and do not commit an IEA extract.

`contrib/` is gitignored reference code for datasets that are not in this release. Do not import it from `src/renweb`.

Shares are fractions. Energy results are terajoules. Do not apply a blanket "labelled TJ but actually PJ" correction: the bulk file's TJ column is terajoules, except electricity output, where it is gigawatt-hours. The check is in `renweb.warehouse.web_view_sql`.
