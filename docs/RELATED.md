# Other tools for the World Energy Balances

The balances themselves are a paid IEA product. See the [product page](https://www.iea.org/data-and-statistics/data-product/world-energy-balances). None of the projects below redistribute the extract. Each one expects you to supply a file you have licensed.

This package does not depend on them. They answer different questions, and taking any of them on would pull in a modelling stack this tool does not need.

## What each one is for

| Tool | Language | What it reads | What it produces | Fit with this package |
| --- | --- | --- | --- | --- |
| IEA-Renweb (this package) | Python | Fixed-width `WORLDBIG*.TXT`, and the long SDMX or OECD CSV (`COUNTRY`, flow, product, year, value, unit) | Renewable, fossil, and nuclear shares, and the power, heat, transport, buildings, industry, and agriculture split, in DuckDB | — |
| [message-ix-models](https://github.com/iiasa/message-ix-models) `tools.iea.web` | Python | The same `WBIG1.zip` / `WBIG2.zip` fixed-width files, and the older OECD iLibrary CSV (editions it has been pointed at: 2021–2024) | A pandas frame or a [genno](https://github.com/khaeru/genno) quantity for [MESSAGEix](https://docs.messageix.org/) scenarios | Closest Python reader. Use it if the next step is a MESSAGEix model. Use renweb if the next step is the renewable-share tables. |
| [IEATools](https://github.com/MatthewHeun/IEATools) | R | The wide extended-balances CSV, with a year in each column and a two-line header (`,,TIME` then `COUNTRY,FLOW,PRODUCT`) | A tidy data frame, then a physical supply-use table | Different file layout and a different question (the energy conversion chain, including useful energy). It does not compute the shares in [METHODOLOGY.md](METHODOLOGY.md). |
| [Recca](https://github.com/MatthewHeun/Recca) and [ECCTools](https://github.com/earamendia/ECCTools) | R | The tidy frame from IEATools, not the raw file | Exergy and multi-region supply-use analysis | Downstream of IEATools. Not a loader. |
| [sdmx](https://sdmx1.readthedocs.io/) (`sdmx1` on PyPI) | Python | SDMX-ML, SDMX-JSON, SDMX-CSV, and SDMX-REST services (OECD, Eurostat, IMF, World Bank, and others) | pandas objects | A general SDMX client. The IEA .Stat service is not one of its built-in sources, and the extended balances file is too large for a row-at-a-time client. renweb streams that CSV with DuckDB instead. |
| [opensdmx](https://github.com/ondata/opensdmx) | Python | SDMX-REST (Eurostat, OECD, ECB, and others) | Polars frames | Same limit: a REST client, not a reader for the licensed balances file. |

Documentation for the message-ix reader, including the note that the data are proprietary: [Tools for specific data sources](https://docs.messageix.org/projects/models/en/stable/api/data-sources.html). IEATools is documented at [matthewheun.github.io/IEATools](https://matthewheun.github.io/IEATools/).

## How this reader differs

Two file details from those projects are handled here.

The OECD iLibrary CSV, which message-ix-models still loads, names the unit column `MEASURE` and the flag column `Flag Codes`. Ingest accepts those names as well as the current SDMX names (`UNIT`, `OBS_VALUE`, `TIME_PERIOD`, `ENERGY_BALANCE_FLOW`, `ENERGY_PRODUCT`).

IEATools is the reference for the wide year-column CSV. That layout uses full names ("Production", "Hard coal") rather than the balance codes the calculations need (`INDPROD`, `HARDCOAL`). This package does not read it. If that is the only file you have, IEATools is the tool that matches it. The fixed-width bulk file and the SDMX CSV are the inputs here.

Two choices in the other readers were not followed.

message-ix-models converts the fixed-width file by splitting each line on repeated spaces, and its usual query keeps the `TJ` measure only. On the current bulk file the fields are fixed at 16 characters, and for electricity output the column labelled TJ holds gigawatt-hours. Splitting on spaces happens to work for the short example lines, and filtering to `TJ` would treat those gigawatt-hours as terajoules. The unit check in [METHODOLOGY.md](METHODOLOGY.md) is the correction.

IEATools maps the missing markers `..`, `x`, and `c` to zero, because the supply-use matrices need a number in every cell. Here those markers stay null. A missing flow is not a measured zero.

Beyond 2020 / IVT files are not read by this package or by `tools.iea.web`. The IEA moved the primary distribution to .Stat in January 2025; the product page still offers the fixed-width text and a code mapping.
