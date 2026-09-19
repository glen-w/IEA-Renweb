# IEA World Energy Balances: format changes and how to absorb them

The balances are revised twice a year (an April early release, then a July edition with full geographical coverage). Most of what changes each edition is coverage, a data year, and membership of aggregates. The file layout is not rewritten from scratch every year. What does break a parser is a smaller set of step changes: the container the files are shipped in, the code vocabulary, and the flag/qualifier column. Those are announced in each edition's "Changes from last edition" section. Read that section before pointing a loader at a new file.

This note is from three places: the IEA's own edition documentation, the archived loaders and the `iea_codes_update_2025.csv` crosswalk, and the Slack export (May 2018 – September 2025, 243,783 messages, including the `#iea` channel). The Slack export is useful for the years before the public notes, and almost silent on the 2025–2026 break.

## Timeline

| When | What changed | Where it is written down |
| --- | --- | --- |
| Through at least mid-2021 | Delivery is a Beyond 2020 `.ivt` file. It needs the Beyond 2020 application, and the practical export path is "save active sheet as Excel". The extended balances file is `WBIG.IVT`; conversion factors are `WCONV.IVT`. | Slack, 4 Apr 2019 (Beyond 2020 file shared); 13 Nov 2019 (WEB 2019, request for `WCONV.IVT`); 18 Jun 2021 (WEB 2020 still shipped as `.ivt`). |
| 2019, observed not specified | A WEB 2019 extract was described internally as values "in various natural units (depending on the product)", needing `WCONV.IVT` to reach toe. Official balances documentation of later editions states the balances themselves are in ktoe and TJ; natural units are the World Energy Statistics product. Treat a natural-unit extract as a different product, not as a balances file with a unit column missing. | Slack, 13 Nov 2019. |
| 2021 (World Energy Outlook, not the balances) | WEO's reported base unit moved from million tonnes of oil equivalent to exajoules. Do not apply that change to WEB rows. | Slack, `#iea`, 12 Oct 2021, citing the IEA's "what to expect from the new WEO 2021". |
| 2023 edition | Still `WBAL.IVT` / `WBIG.IVT` / `WIND.IVT` / `WCONV.IVT`. "Changes from last edition" is coverage (provisional 2022, Lithuania in the IEA total), not a layout change. | [WORLDBAL documentation](https://iea.blob.core.windows.net/assets/0acb1453-1221-421b-9131-632ce71a4c1a/WORLDBAL%5FDocumentation.pdf). |
| 2024 edition, legacy files | Same four IVT files, plus a parallel TXT distribution of the same tables. Short mnemonic codes (`ELECTR`, `AGRICULT`, `HARDCOAL`). | [TXT and IVT edition documentation](https://iea.blob.core.windows.net/assets/dd20344e-67f9-4004-a744-ea8c1f925d7c/WORLDBAL_DocumentationTXTandIVTedition.pdf). |
| January 2025 | Primary platform moves from Beyond 2020 (IVT) to [.Stat Data Explorer](https://www.iea.org/data-and-statistics/data-product/world-energy-balances). Dataset short names change "to improve harmonization across IEA datasets". A mapping between old and new codes is published on the product page ("World Energy Balances .StatSuite mapping"). TXT files continue, but on the new codes, and gain a qualifier column. | April 2025 edition documentation, "Changes from last edition". |
| 2025 qualifiers | Records are labelled `A` normal, `I` imputed (includes IEA aggregations, conversions, and estimates), `O` missing, `M` not applicable, `P` provisional, `C` confidential, `D` definition differs, `N` not qualified. Confidentiality is also a `CONF_STATUS` column in the CSV. More detailed qualification for non-questionnaire countries starts in 2019. | Same April 2025 note; repeated in the [April 2026 documentation](https://iea.blob.core.windows.net/assets/474ea947-f44f-496b-9285-82708cdbeb42/EARLYBAL_Documentation_April2026.pdf), "Qualifiers". |
| April 2026 edition | TXT files are discontinued. Bulk download is CSV, "fully aligned with the structure and content of the .Stat Data Explorer". | April 2026 documentation, "Changes from last edition". |
| Ongoing, every edition | Country and aggregate membership moves (EU composition, IEA accession and association, fiscal-year countries). A country can be announced and still be absent from that edition's aggregate because the file was already frozen. | Geographical coverage subsection of each edition note. Latvia (Oct 2024) is in the April 2025 note; Romania and Viet Nam are named in April 2026 and explicitly not yet in the aggregate. |

The Slack export's `#iea` channel (created 24 Feb 2020) is press and positioning, not data layout. The only unit change discussed there is the 2021 WEO switch to exajoules. Nobody in the export discusses the January 2025 code rename or the 2026 end of TXT. Those have to come from the edition PDFs and from diffing files.

## The two layouts in the archive

Both are on disk under the archived `gsr python` data folder. They are not interchangeable.

**Bulk TXT** (`WORLDBIG1.TXT`, `WORLDBIG2.TXT`, inside `WBIG1.zip` / `WBIG2.zip`). One record per line, whitespace-separated, not two lines per record:

```text
WORLD           HARDCOAL        1960            INDPROD         KTOE            ..
WORLD           HARDCOAL        1960            INDPROD         TJ              ..
```

Fields are country, product, year, flow, unit, value. Missing markers seen in this file are `..` (and the loaders also treat `x`, `c`, and blank as missing). Codes are the short mnemonics. Each flow is stored twice, once in `KTOE` and once in `TJ`.

An archived parser (`iea_web_ingestion.py`, docstring "2024 Format Change") claims the 2024 file is two lines per record, line 1 country/product/year/flow and line 2 unit/value/flag. That does not match `WORLDBIG1.TXT`. Pairing lines would attach the next record's fields to this one. Do not revive that parser.

**SDMX CSV** from .Stat, file dated 29 Jun 2025 (`OECD.IEA,WORLDBIG,1.0,...csv`). A header row of identifiers and labels, then `DATAFLOW` rows. Columns include `COUNTRY`, `ENERGY_BALANCE_FLOW`, `ENERGY_PRODUCT`, `TIME_PERIOD`, `OBS_VALUE`, `QUALIFIER`, `UNIT`, `MEASURE`, `CONF_STATUS`, plus the human-readable twin of each code (`Country/Region`, `Flow`, `Product`). Codes are the long form (`NE_MINING`, `BIOGASOLINE`). `MEASURE` is `TJ_BAL` ("Balance in energy units: TJ") rather than a bare `TJ`. Empty `OBS_VALUE` with qualifier `O` is a missing point, not a zero.

The vendored crosswalk `iea_codes_update_2025.csv` has 176 old-to-new pairs, 75 of them real renames. Examples that calculations depend on: `ELECTR` → `ELECTRICITY`, `AGRICULT` → `AGRI_FOREST`, `GEOTHERM` → `GEOTHERMAL`, `MRENEW` → `RENEWABLES_TOTAL`, `AVBUNK` → `BUNKERS_AVIATION`, `NONENUSE` → `NE_TOT`. About a hundred codes are unchanged (`TFC`, `ELOUTPUT`, `HYDRO`, `HEAT`, `ROAD`). An August 2025 impact note counted 89 renames against a slightly wider list in the migration script; the CSV is the list to vendor.

## Units, which are not a format change but will be misread as one

In the bulk TXT, energy flows really are in TJ. France 2022 `TOTAL` / `TFC` is 140,989.99 ktoe and 5,902,969 TJ, and 140,989.99 × 41.868 = 5,902,969. A loader that "corrects" TJ to PJ by multiplying by 1,000 is wrong for this file.

Electricity output is the exception, and it is visible in the row rather than in the header. France 2022 `HYDRO` / `ELOUTPUT` is 45,521 in both the ktoe column and the TJ column, which is the GWh figure, not terajoules. The edition notes have always said electricity and heat output are published in GWh, TJ, and ktoe; the TXT stores the GWh figure under the TJ label for those flows. Detect it (TJ value equals ktoe value, or the measure is an output flow) instead of keeping a hardcoded flow-name list, because those names are exactly what got renamed in 2025.

## How to handle the next change

1. **Sniff the file, then pick a reader.** `.ivt` is out of scope (it needs Beyond 2020). A first line of `STRUCTURE,STRUCTURE_ID,...` or a `DATAFLOW` record is the .Stat CSV. A line of whitespace-separated tokens with a four-digit year and a unit of `KTOE`/`TJ`/`GWH` is the legacy TXT. Anything else fails the ingest with the first line attached to the error, rather than being forced through a parser.

2. **Store the edition.** A `source` row should keep filename, sha256, edition (from the documentation PDF or the file date), which reader ran, row count, and the set of product and flow codes actually seen. Reloading the same sha256 is a no-op. A new sha256 for the same edition replaces that edition's rows. April and July of the same year are different editions; do not mix them in one result set.

3. **Canonical codes are the current .Stat identifiers.** Legacy short codes pass through the crosswalk on the way in. Unknown codes are loaded as-is and listed in the ingest report. They are not dropped and not guessed. A code that disappears between editions is a warning, not a silent zero, because a rename looks exactly like a disappearance (`AGRICULT` vanishing and `AGRI_FOREST` appearing).

4. **Diff before compute.** Compare this edition's column set and code set with the previous ingested edition. New column, missing column, or a code-set delta above a small threshold stops the pipeline and prints the delta. Computing renewable shares on a half-mapped code set is worse than refusing to compute.

5. **Update the crosswalk from the IEA's mapping file, not by hand.** The product page publishes "World Energy Balances .StatSuite mapping". Vendor that file, dated, next to the edition it belongs to. Keep old crosswalks. A methodology version on result rows separates a crosswalk change from a data change.

6. **Keep raw units. Normalise in a view.** Every raw row is stored with its unit and its qualifier. The TJ view is built by the ktoe cross-check (ratio about 41.868) for energy flows, and by the electricity/heat-output exception above. A row that matches neither rule is flagged and left out of the view.

7. **Flags are data.** `..`, `x`, `c`, blank, and qualifiers `O` and `M` are NULL. `C` stays NULL and is marked confidential. `P`, `I`, `D`, `N` are kept so a provisional or imputed point can be filtered later. A new qualifier letter must not be parsed as a number.

8. **Aggregates are their own series.** `OECDTOT`, `EU27_2020`, `IEAFAMILY`, and `WORLD` are stored under the code the file uses. Do not recompute them from a hardcoded membership list. Membership is one of the things the edition note changes.

9. **When a container dies, add a reader, do not rewrite the warehouse.** The 2026 CSV is the same facts as the .Stat export already in the archive, with identifier columns, a measure code, and qualifiers. A new reader should land rows in the same `web_raw` shape (country, product, flow, year, unit, value, qualifier, source). Calculations never see the file format.
