# IEA-Renweb: project review and stocktake

23 September 2026. Read against commit `493355e` (`v0.1` on `main`, in sync with `origin/main`) and the working tree. Tests were re-run for this note: 57 passed, 1 skipped, 93% statement coverage of `src/renweb`.

This is a stocktake of the tool as it stands. It is not a methodology revision.

## Where it stands

IEA-Renweb is a small, finished-shaped library and command-line tool. It loads a licensed World Energy Balances extract into a DuckDB file outside the git tree, normalises units in a view, and writes renewable, fossil, and nuclear statistics. Package version is `1.0.0`. Formula version on every result row is `method_version` `2`. The public surface is the CLI (`ingest`, `compute`, `validate`, `export`, plus two optional ingests), the Python API, a read-only marimo notebook, and a static landing page.

The boundaries in `AGENTS.md` hold in the code: ingest does not compute, compute does not parse files, validate does not invent values, export does not recompute, World Bank and IRENASTAT attach extra rows and leave the IEA identities alone, and the notebook opens the warehouse read-only.

What is solid is the loader, the unit check, the total-final-consumption identity, and the test harness around synthetic files. What is still open is everything that depends on a real extract or on a classification table: edition mixing, the OECD membership list, the fossil-import product list, and the silent own-use fallback. Those are the items that can move a published number without a failing test.

The git history is one squashed commit, message `v0.1`, dated 19 September 2026, tag `v0.1`. The package, the landing-page footer, and `method_version` have all moved on from that tag. Release identity is the first housekeeping gap.

## Inventory

| Piece | What it is |
| --- | --- |
| Package | `iea-renweb` 1.0.0, import name `renweb`, Python ≥ 3.11, MIT, hatchling |
| Runtime dependencies | duckdb, pyarrow, typer, rich, pydantic |
| Extras | `xlsx` (openpyxl), `worldbank` and `irena` (httpx), `notebook` (marimo, plotly, pandas), `dev` |
| CLI | `renweb` → `renweb.cli:main` |
| Warehouse | `$RENWEB_DATA` or `~/Documents/renweb_data/renweb.duckdb` |
| Source | 22 Python modules under `src/renweb`, about 3,100 lines |
| Tests | 9 files, 57 tests, about 1,400 lines. One integration test, skipped unless `RENWEB_IEA_DIR` is set |
| Vendored refdata | 8 files, 839 lines, shipped inside the wheel |
| Docs | `README.md`, `docs/METHODOLOGY.md`, `docs/RELATED.md`, `docs/iea-format-changes.md` |
| Notebook | `notebooks/quicklook.py`, marimo 0.24.2, loopback port 2719 |
| Website | `website/`, GitHub Pages workflow, live at glenwright.earth/IEA-Renweb |
| Tracked files | 66 |

`pydantic` is declared and never imported. `src/renweb/__main__.py` exists so `python -m renweb` works; the tests do not import it.

Uncommitted work on this tree is cosmetic: SVG marks on the four feature headings in `website/index.html`, and the matching rules in `website/styles.css`. The library is unchanged from `v0.1` as committed.

Local paths that are deliberately untracked: `/data/` (extracts), `*.duckdb`, `/notes/`, `.cursor/commands/`. `notes/heat-share-calculation.md` is a 19 September working note about an electricity-for-heat formula. The current tests forbid the variables that note describes. Treat the note as history of the cut, not as a description of `method_version` 2.

## How a run actually moves

```text
WORLDBIG*.TXT / zip / SDMX or OECD long CSV
        │  sniff, sha256, crosswalk, ISO3
        ▼
   web_raw  +  source          (one row per country, product, flow, year, unit)
        │  view: ktoe↔TJ check, GWh exception
        ▼
   web.value_tj, unit_status
        │  Python, one country-year at a time
        ▼
   results (method_version = 2)
        │
        ├─ validate  (findings; exit 1 only on a broken TFEC identity)
        └─ export    (parquet, csv, optional xlsx)

Optional, either order relative to compute:
   World Bank API  → wb_indicators, wb_income
   IRENASTAT / CSV → capacity
        │  attach_optional, only where economy_tfec_tj already exists
        ▼
   extra result rows, same method_version
```

`compute` deletes existing rows for this method version in the requested country-year scope, inserts the new batch through Arrow, then reattaches optional variables. A second `ingest` of the same bytes is a no-op. A changed file with the same name replaces that file's `web_raw` rows.

A synthetic non-OECD country-year with the fixture in `tests/test_formulas.py` writes 178 result variables. Shares whose denominator is zero are omitted, so a fuller year writes the industry-subsector renewable shares on top of that. Optional ingest can add 6 World Bank variables and 7 capacity variables. Income group stays in `wb_income` and is not a result variable.

Variable families on that fixture:

| Prefix | Rows | Role |
| --- | ---: | --- |
| `raw_*` | 36 | Balance inputs after the unit view: TFC, output, shares, sector totals |
| `adjusted_*` | 27 | TFEC, technology-adjusted electricity, fossil residual, sector allocation |
| `enduse_*` | 17 | Buildings, industry, agriculture, transport, plus `enduse_unallocated_tj` |
| `power_*` | 15 | Generation split. Fossil generation is the residual of total − nuclear − renewables memo |
| `industry_*` | 15 | Industry bundle and seven subsectors |
| `economy_*` | 13 | The same TFEC totals under the economy names, plus TES and the fossil import ratio |
| `buildings_*` | 12 | Residential + commercial |
| `adjustment_*` | 9 | Eight technology multipliers and `adjustment_used_fallback` |
| `transport_*` | 9 | Biofuels plus transport electricity × generation renewable share |
| `heatbio_*` | 7 | Bioenergy remainder by sector, and traditional biomass |
| `heat_*` | 7 | District heat, solar thermal, geothermal, modern bioenergy |
| `agriculture_*` | 6 | Agriculture + fishing |
| `sectoral_*` | 4 | Sector shares of TFEC |
| `renewable_electricity_share` | 1 | Adjusted renewable electricity / final electricity, else the generation share |

## What method version 2 calculates

Documented in `docs/METHODOLOGY.md` and implemented in `src/renweb/compute/formulas.py`.

- **TFEC** = `TFC(TOTAL) − NONENUSE(TOTAL)`. Fossil TFEC is the residual, so fossil + nuclear + renewable equals TFEC by construction.
- **Units.** Ordinary flows: TJ column kept when `TJ / ktoe` is within 2% of 41.868. Electricity output: when the two columns hold the same figure, that figure is gigawatt-hours and is multiplied by 3.6. Anything else with both columns is `suspect` and dropped from compute. The check lives in `web_view_sql`, detected from the numbers, not from a flow-name list.
- **Renewable electricity in TFEC** is the sum of technology outputs times own-use multipliers, plus biopower times its multiplier. The renewables memo is not multiplied again on top of that sum.
- **Traditional biomass** is residential primary solid biofuels plus residential charcoal, and only when the country is absent from `oecd_members.json`. OECD residential solid biofuels count as modern. An aggregate code is not a member, so `WLD` residential solid biofuels all count as traditional. The methodology already says that overstates the world row.
- **Sectors.** Each sector TFEC subtracts a pro-rata slice of non-energy use even when the sector totals already exclude it. The gap is `enduse_unallocated_tj`. Transport renewables are biofuels plus transport electricity times the generation renewable share, and do not use the transport renewables memo.
- **Own-use multipliers.** Built from losses and own-use flows, plus conversion offsets (hydro −0.01, nuclear / geothermal / CSP −0.06, other thermal −0.07, solar PV / ocean / wind 0). If the base is zero, or any multiplier falls outside 0.5–1.5, the run substitutes `adjustment_factors.json` and sets `adjustment_used_fallback` to 1.

Removed, and pinned by `test_heat_share_assumptions_are_not_results`: electricity-for-heat assumption variables, `renewable_electricity_heat_*`, `sectoral_electricity_for_heat_tj`, `sectoral_electricity_excluding_heat_and_transport_tj`, `buildings_district_heat_bioenergy_tj`, and `assumption_bioenergy_share`. The 0.95 district-heat split and the 4% / 11% heat-share constants are not in this tree. `method_version` 2 is that cut.

Still inside the main identity, and still assumptions rather than balance rows: the own-use offsets and their fallback table, the OECD membership switch, and the pro-rata non-energy subtraction.

## Loader and warehouse

Tables created in `connect`: `source`, `web_raw`, `results`, `wb_indicators`, `wb_income`, `capacity`, plus the `web` view. Schema changes are `CREATE TABLE IF NOT EXISTS`. A new table appears on the next connect. A changed column on an existing table does not migrate. There is no warehouse schema version.

`source` stores sha256, filename, format (`txt` or `csv`), row counts, unmapped-country count, and `ingested_at`. It does not store an edition name, a code list, or which reader revision ran.

`web` groups `web_raw` by country, product, flow, and year, across every loaded file. Two editions left in one file are combined with `max()` per unit. `docs/iea-format-changes.md` says April and July of the same year must not share a result set. The code does not enforce that.

Canonical codes are the 2025 `.Stat` names via `code_crosswalk.csv` (176 old→new rows, including identities). Unknown codes pass through. Country codes become ISO3 via `iea_codes.json` (191 rows, 32 of them aggregates) and `country_crosswalk.csv`. An unmapped country code is kept and counted.

Fixed-width records are one 101-character line: country, product, year, flow, unit, value. Markers `..`, `x`, `c`, blank, and `-` become null. The long CSV accepts current SDMX names and the older OECD names (`MEASURE`, `Flag Codes`). `TJ_BAL` and `GWH_BAL` map onto `TJ` and `GWH`.

`docs/iea-format-changes.md` lists nine rules for the next IEA layout change. The tree follows the sniff, the crosswalk, raw-units-plus-view, aggregate codes kept as published, and one `web_raw` shape for every reader. It does not yet diff the code set before compute, store the edition, keep dated crosswalks side by side, or list unmapped product and flow codes in the ingest report. Qualifiers are stored in `flag` when a qualifier column is present. Qualifier letters `O` and `M` are not given special null handling beyond a non-numeric observation already failing `try_cast`.

## Optional inputs

World Bank (`ingest-worldbank`) replaces `wb_indicators` and `wb_income` from the API, then attaches population, two GDP series, TFEC per capita, renewable TFEC per capita, and TFEC per PPP GDP. A zero or missing denominator omits the ratio. Income is queryable only from `wb_income`.

IRENA (`ingest-irena`) replaces `capacity` from IRENASTAT JSON-stat or from a CSV (`country, year, technology, grid, capacity_mw`). On-grid and off-grid rows are summed into seven megawatt variables. Capacity is not added into TFEC.

Both commands call `attach_optional` immediately, so they can run before `compute` and simply attach zero rows until IEA totals exist. A later `compute` attaches them again.

## Checks, tests, and what they do not see

`renweb validate` returns at most 200 findings.

| Check | Severity | Rule |
| --- | --- | --- |
| `tfec_identity` | error, exit 1 | `adjusted_tfec_tj` equals `raw_tfc_total_tj − raw_non_energy_use_tj` within 1e-6 relative |
| `share_bounds` | warning | any `*_share` below −0.01 or above 1.15 |
| `tfec_shares` | warning | fossil + nuclear + renewable economy shares within 0.15 of 1 |
| `electricity_output_shares` | warning | the same three power shares within 0.10 of 1 |
| `non_negative` | warning | a terajoule result below −1e-6 |
| `year_on_year` | warning | a `*_tj` series moves by more than 300% when the previous value is above 1 TJ |

The TFEC identity is true by construction in `compute_one` (`tfec = tfc - non_energy`). The error check confirms the writer did not drop a row. It does not confirm the extract was read correctly. Share tolerances of 0.10 and 0.15 will pass a country whose three shares are materially off. Fallback multipliers, suspect-row rates, unmapped codes, and edition mixing are not checks.

CI (`.github/workflows/test.yml`) on every push and pull request: `uv sync --extra dev --extra notebook`, pytest, ruff, black, mypy. Notebooks are excluded from ruff and black. Coverage is not gated. The live-extract test does not run in CI, which is the right licence boundary.

Coverage of the library is 93% (1,463 statements, 97 missed). `formulas.py`, `dag.py`, `optional.py`, and `notebook.py` are fully covered on synthetic frames. The thin spots are the real HTTP path in `ingest/http.py` (36%), the xlsx writer, and `iea_regions()` which nothing calls.

The only assertion against a real extract is France 2022 `TOTAL` / `TFC`: `value_tj ≈ 5,902,969` and `unit_status` in `{tj_checked, tj_unchecked}`. That locks the "TJ column is terajoules" decision for one cell. It does not lock electricity-output detection, a renewable share, or a sector total on that file.

There is no committed small fixture file. Tests build lines with `format_fixed_width`. That matches the project card.

## Defects and unused material

These are the items that can change a number, or that look like method and are not wired up.

**OECD list is four members short.** `oecd_members.json` has 34 ISO3 codes. The current OECD membership is 38. Missing: Estonia (`EST`, joined 2010), Slovenia (`SVN`, 2010), Latvia (`LVA`, 2016), Lithuania (`LTU`, 2018). Chile, Colombia, Costa Rica, and Israel are present. Under the documented rule, residential solid biofuels in those four countries are classified as traditional biomass. `is_oecd` is a set lookup with no year, so the list is also ahistorical: a country is modern for every year once it appears, including years before accession.

**Fossil import ratio uses a short product list.** `fossil_fuels.json` has 18 legacy codes (coals, crude, residual fuel oil, refinery gas, aviation gasoline, jet gasoline, LPG, natural gas, blast-furnace gas, two nonspecific codes). `canon` maps them forward. The crosswalk also contains motor gasoline, gas/diesel oil, jet kerosene, naphtha, petroleum coke, ethane, and bitumen, and none of those are in the fossil list. The memo fallback `IMPORTS` / `MFOSSIL` runs only when the listed sum is exactly zero, and `MFOSSIL` itself is not in the crosswalk, so a current long code would not match it either. Any country that imports one listed product and also imports diesel will have a ratio that ignores the diesel. `economy_fossil_import_ratio` is outside the TFEC identity, so validate will not catch it.

**Own-use fallback is silent in the results.** A failed identity substitutes eight constants (hydro 0.99, geothermal and CSP and nuclear 0.94, biopower 0.93, solar PV, ocean, and wind 1.0) and records `adjustment_used_fallback = 1`. Adjusted renewable electricity enters `adjusted_tfec_renewable_tj`. A country whose balance does not close still receives a full renewable total. The flag is a result row, not a validation finding.

**Edition mixing.** Loading a second file with a different name adds rows. The `web` view then takes `max(TJ)` and `max(ktoe)` across sources for the same country-year-flow-product. A July file and an April file in one warehouse can produce a hybrid year. `results` has no `source_id`, so export cannot say which edition a number came from. Export also writes every `method_version` still in the table; only `compute`'s delete is scoped to version `2`.

**`conversion_factors.json` is unused and one factor is inverted.** Nothing in `src/` reads it. The tests only check that the file is present. `TJ → PJ` is 0.001, which is right. `TJ → EJ` is 1,000,000, which multiplies the wrong way: 1 EJ = 1,000,000 TJ, so the factor from TJ to EJ is 1e-6. Leaving the file in refdata makes it look like a supported conversion. The methodology already forbids a blanket TJ-to-PJ rescale of the bulk file.

**`iea_regions.json` is unused.** `iea_regions()` loads it and has no caller. Region membership does not affect a result. Coverage misses the function body for that reason.

**Compute materialises the view in Python.** `dag.compute` fetches every non-suspect `web` row in scope and folds it into a dict per country-year before `compute_one`. That is clear and it is what the tests exercise. A full extended extract (countries × years × products × flows × two units) is a large in-memory pass, and a partial `--country` run still cannot see rows the view has already collapsed across editions.

**DuckDB is single-writer.** The notebook says so, and a read-only connection still conflicts with `ingest` or `compute`. There is no CLI `--db` flag; the path is `RENWEB_DATA` or the default under `~/Documents/renweb_data`.

**CLI logging.** Ingest uses `logging.info` for skips and duplicate drops. The CLI never configures logging, so those lines stay invisible unless the caller configures a handler. The Rich table is the user-facing report.

## Surfaces around the library

The notebook (`notebooks/quicklook.py` plus `renweb.notebook`) shows sources, the unit-status counts, one country's economy shares and sector renewable shares, up to six countries on one variable, a choropleth, and validation findings. It writes nothing. Headless marimo runs are in the test suite, including an empty warehouse.

The website is a static landing page: what the tool does, that the extract stays with the user, install commands, a link to GitHub. Pages deploys `website/` on changes under that directory. Footer says version 1.0.0. No Sphinx build.

`docs/RELATED.md` positions this package against message-ix-models `tools.iea.web`, IEATools, Recca, ECCTools, and the SDMX REST clients. The distinguishing claims match the code: fixed-width fields rather than a whitespace split, the GWh detection, and missing markers kept as null.

Licence split is clean. The tool is MIT. The balances are not in the repo, `.gitignore` anchors `/data/` at the root so `src/renweb/refdata/data/` still ships, and the README states the IEA Terms of Use for Non-CC Material. A shared app or a model that redistributes derived data still needs its own agreement; nothing in this repo publishes derived balances.

## Release identity

| Label | Value | Where |
| --- | --- | --- |
| Package | 1.0.0 | `pyproject.toml`, `renweb.__version__`, website footer |
| Formula | 2 | `METHOD_VERSION` in `formulas.py`, methodology |
| Git tag | `v0.1` | only tag, on the only commit |
| Commit | `493355e`, 19 September 2026, message `v0.1` | `main` = `origin/main` |
| Author | Glen | `pyproject.toml`, MIT copyright 2026 |

`method_version` and the package version answer different questions, and both are ahead of the tag. There is no changelog, no schema version, and the project card records `release_governance: none`.

## What to do next, in order

1. **Fix the four missing OECD codes** (`EST`, `SVN`, `LVA`, `LTU`) and decide whether membership is a single set or a year-aware one. This changes traditional biomass and modern renewables for those countries. Bump `method_version` if the published series should be distinguishable from version 2.
2. **Replace or drop the fossil-import product list.** Either sum the fossil memo product under its current code, or expand the list to the oil products already in the crosswalk. A partial sum that suppresses the memo fallback is the worst of the two behaviours.
3. **Stop a second edition from merging in `web`.** Store an edition (or require one warehouse file per edition) and make the view read one source. Put `source_id` or the edition on `results` if export needs to say where a number came from.
4. **Turn `adjustment_used_fallback = 1` into a validation warning**, or omit adjusted electricity when the own-use identity fails, and bump `method_version` if the fallback stops being the default.
5. **Remove or quarantine `conversion_factors.json`**, and either call `iea_regions()` from somewhere real or stop shipping the file. Drop the unused `pydantic` dependency when the lockfile is next refreshed.
6. **Tag `v1.0.0` to match the package** once the three data issues above are either fixed or explicitly deferred in `METHODOLOGY.md`. Add a one-line changelog. The squashed history cannot carry that story; the tag can.
7. **Keep the live-extract test narrow**, and add one more cell to it when an extract is available: France 2022 hydro electricity output should land as `electricity_output_gwh` and about 45,521 × 3.6 TJ. That is the other unit rule, and the synthetic tests only approximate it.

Items 1–3 change numbers. Items 4–7 change trust in the numbers. The loader, the TFEC identity, the sector split, and the optional World Bank and IRENA paths can stay as they are while that list is worked.
