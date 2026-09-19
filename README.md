# <img src="website/logo.png" alt="" width="36" height="36" /> IEA-Renweb

Tools for turning an IEA World Energy Balances extract into renewable energy statistics. It loads the bulk fixed-width file or the SDMX CSV into DuckDB, checks units, and calculates total final energy consumption, renewable and fossil shares, and the power, heat, transport, buildings, industry, and agriculture splits.

This is a library and a command line tool. There is no hosted web application; an optional local [marimo](https://marimo.io) notebook for a quick look at the warehouse is in `notebooks/`.

Hosted landing: [glenwright.earth/IEA-Renweb](https://glenwright.earth/IEA-Renweb/) ([`website/`](website/)).

## The IEA extract is yours

[World Energy Balances](https://www.iea.org/data-and-statistics/data-product/world-energy-balances) is a paid IEA data product. This repository is the toolset only. The balances are not included, and they must not be added: the licence is the IEA's Terms of Use for Non-CC Material, not an open licence. A shared application or a model that redistributes derived data needs a separate agreement. Buy or subscribe on the product page, then point the commands below at the files you downloaded.

The July 2026 edition covers the world, 156 countries, and 34 regional aggregates, in thousand tonnes of oil equivalent and terajoules. Series generally run from 1971 (1960 for OECD countries) through 2024, with preliminary 2025 figures for selected countries, products, and flows. The IEA updates it twice a year, in April and July. Electricity and heat output are also published in gigawatt-hours. The extended balances are 68 products and 98 flows. When you cite the database, the IEA asks for: IEA, *World Energy Balances*, IEA, Paris, <https://www.iea.org/data-and-statistics/data-product/world-energy-balances>, Licence: Terms of Use for Non-CC Material.

This tool reads two distributions of that extended table:

- `WORLDBIG*.TXT`, the fixed-width bulk file (often shipped as `WBIG1.zip` and `WBIG2.zip`)
- a long CSV of the same table, either the current SDMX export or the older OECD iLibrary export

Summary balances, the indicators file, conversion factors, and Beyond 2020 / IVT files are part of the product and are not read. The wide CSV with one column per year is the input for [IEATools](https://github.com/MatthewHeun/IEATools), not for this package. A comparison with the other open-source readers is in [docs/RELATED.md](docs/RELATED.md).

The two editions this tool does read use different code lists. Ingest maps the older codes onto the current ones.

## Install

Python 3.11 or newer, and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

The warehouse is a DuckDB file outside the git tree. The default path is `~/Documents/renweb_data/renweb.duckdb`. Set `RENWEB_DATA` to a `.duckdb` file or to a directory if you want it somewhere else.

## Command line

```bash
uv run renweb ingest /path/to/WBIG1.zip
uv run renweb compute --country FRA --year 2022
uv run renweb validate
uv run renweb export ./out --format parquet --format csv
```

`ingest` accepts a file or a directory. Loading the same bytes twice is a no-op. A changed file with the same name replaces its rows.

`compute` with no country or year runs every country-year in the warehouse. Shares are fractions: `0.25` means 25 percent. Energy is in terajoules.

xlsx export needs the optional extra: `uv sync --extra xlsx`.

Population, GDP, and income grouping are optional:

```bash
uv sync --extra worldbank
uv run renweb ingest-worldbank
uv run renweb compute
```

Installed electricity capacity is optional:

```bash
uv sync --extra irena
uv run renweb ingest-irena
uv run renweb ingest-irena /path/to/capacity.csv
uv run renweb compute
```

`ingest-worldbank` talks to the World Bank API. `ingest-irena` talks to IRENASTAT, or reads a CSV with columns `country, year, technology, grid, capacity_mw`. Both extras need `httpx`. Either command can run before or after `compute`; intensity and capacity result rows are written only for country-years that already have IEA totals.

Income groups are not result variables. Query them from `wb_income`:

```sql
SELECT country, income_level_id, income_level FROM wb_income WHERE country = 'FRA';
```

## Python

```python
from renweb.warehouse import connect
from renweb.ingest import ingest
from renweb.compute import compute

con = connect()
ingest("/path/to/WORLDBIG1.TXT", con)
compute(con, countries=["FRA"], years=[2022])
row = con.execute(
    """
    SELECT value FROM results
    WHERE country = 'FRA' AND year = 2022 AND variable = 'economy_share_renewable'
    """
).fetchone()
```

The normalised balances are in the `web` view (`value_tj`, `unit_status`). Rows whose ktoe and TJ columns disagree, and which are not the electricity-output case, have `unit_status = 'suspect'` and are left out of the calculations.

## Notebook

An optional marimo notebook gives a quick look at the warehouse: what is loaded and the unit check, one country's shares over time, up to six countries on one variable, a world map of one share for one year, and the validation findings. It reads the warehouse and writes nothing.

![Warehouse table after ingest, with balance row counts](docs/images/notebook-warehouse.png)

The country view plots economy shares of total final energy consumption, then renewable share by sector.

![Country quick-look: economy shares of TFEC](docs/images/notebook-country.png)

![Renewable share by sector](docs/images/notebook-sector-shares.png)

```bash
uv sync --extra notebook
uv run marimo run notebooks/quicklook.py --host 127.0.0.1 --port 2719
```

Open `http://127.0.0.1:2719`. Use `marimo edit` only when changing cells. The notebook has no password; keep it on the loopback address.

DuckDB is single-writer, and a read-only connection still conflicts with a writer. Stop the notebook before `renweb ingest`, `compute`, `ingest-worldbank`, or `ingest-irena`, then start it again.

## What the numbers are

The formulas, the unit check, and the traditional-biomass rule are in [docs/METHODOLOGY.md](docs/METHODOLOGY.md). World Bank and IRENASTAT inputs are optional extras; they add intensity and capacity variables and do not change the IEA identities.

## Tests

```bash
uv run pytest
```

An optional check against a local extract:

```bash
RENWEB_IEA_DIR=/path/to/your/extract uv run pytest tests/test_integration.py
```

That test is skipped unless the variable is set, and it does not run in CI.

Ruff and Black are configured to skip `notebooks/`; marimo owns the cell layout there.

## Other readers

Open-source tools that also touch this database, and how they differ, are in [docs/RELATED.md](docs/RELATED.md).

---

<p align="center">
  <a href="https://ko-fi.com/C0C1XK8G" target="_blank" rel="noopener noreferrer"><img height="36" style="border:0;height:36px" src="https://storage.ko-fi.com/cdn/kofi6.png?v=6" alt="Buy Me a Coffee at ko-fi.com" /></a>
</p>

