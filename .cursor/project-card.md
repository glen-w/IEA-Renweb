# Project card

Filled values are inlined in `.cursor/commands/`. Edit both if a value changes. This file is not a slash command.

```yaml
project: IEA-Renweb
package: renweb
src_package: src/renweb
ui_kind: none
ui_port: none
ui_entry: none
sibling_ports:              # never inspect, bind, or kill
  - 8501                    # TranscriptX
  - 8510                    # Transcribe
small_fixture: none yet — build with renweb.ingest.txt.format_fixed_width; do not use a live IEA extract
large_fixture_hint: a user-named IEA balances file (.txt, SDMX .csv, or .zip); do not fake size by duplicating a snippet; do not use ~/Documents/renweb_data unless asked
default_test_cmd: python -m pytest tests/ -q
coverage_cmd: python -m pytest tests/ -q --cov=src/renweb --cov-report=term-missing
architecture_rules:
  - ingest loads balances only; it must not compute statistics
  - compute owns formulas and the DAG; it must not parse IEA files
  - refdata is read-only (codes, countries, assumptions); it must not write the warehouse
  - warehouse is the only DuckDB owner; default path is $HOME/Documents/renweb_data/renweb.duckdb via RENWEB_DATA; probes pass an explicit temp path
  - validate checks results; it does not invent values
  - export writes outputs; it does not recompute
release_governance: none
backup_hub: "$HOME/Documents/code backups"
backup_excludes:
  - data
  - contrib
  - "*.duckdb"
  - "*.duckdb.wal"
  - "*.parquet"
backup_includes: []
verify_paths:
  - src/renweb
  - pyproject.toml
  - docs
  - LICENSE
  - .cursor/commands
staging_prefix: renweb-backup
high_leverage_tests:
  - fixed-width TXT and SDMX CSV ingest
  - code crosswalk and country ISO3 mapping
  - warehouse schema and web view unit pairing
  - compute DAG and formulas
  - validate checks
  - export writers
doc_contracts: none yet; docs/iea-format-changes.md is a format note, not a contract
```
