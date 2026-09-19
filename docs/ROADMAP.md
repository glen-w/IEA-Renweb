# Roadmap

This package stops at the IEA World Energy Balances. Three other inputs were part of the earlier pipeline and are not calculated here. The loaders that fetched them are kept in `contrib/` for reference. That directory is gitignored, it is not installed, and nothing under `src/renweb` imports it.

## World Bank indicators

Population and GDP, so TFEC can be expressed per person and per unit of GDP, plus the income-group classification used to group countries. See `contrib/world_bank_client.py` and `contrib/world_bank_income_loader.py`.

## Capacity

Installed renewable capacity, which the balances do not report. See `contrib/capacity_loader.py`.

## Policy database

A structured policy dataset, with a cleaner and a small command line. See `contrib/policy_loader.py`, `contrib/data_cleaner.py`, and `contrib/cli_policy.py`.

Wiring any of these in means a new source table and new result variables. It should not change the IEA-only identities in [METHODOLOGY.md](METHODOLOGY.md).
