# Methodology

The calculations below use a licensed extract of the IEA [World Energy Balances](https://www.iea.org/data-and-statistics/data-product/world-energy-balances). That database is a paid product and is not in this repository. Population, GDP, installed capacity, and policy data are not inputs. Assumption tables that the balances do not publish (the share of heat met by electricity, a solid-bioenergy share, and fallback electricity multipliers) ship with the package and can be replaced.

Energy results are terajoules. Shares are fractions: `0.25` means 25 percent. A share is omitted when its denominator is zero. `method_version` on every result row is `1`. A change to these formulas bumps that version so a methodology change is distinct from a new extract.

## Codes

Canonical product and flow codes are the current SDMX codes. The bulk fixed-width file still uses the older names (`AGRICULT`, `NONENUSE`, `MRENEW`). Ingest and the calculation frame map those through `code_crosswalk.csv`. Summing two names that map to the same code counts the flow once.

Country codes are mapped to ISO 3166-1 alpha-3 where the extract names a country, and aggregates (`WLD`, `OECDTOT`, `EU27_2020`) keep their own codes. The SDMX country name is accepted as well (`AUSTRALIA` and `AUSTRALI` both become `AUS`). An unmapped code is kept, not dropped.

## Units

The bulk file has a ktoe column and a column labelled TJ.

For ordinary energy flows the TJ column is terajoules. The check is `TJ / ktoe ≈ 41.868`, which is the IEA toe definition (1 toe = 41.868 GJ, so 1 ktoe = 41.868 TJ). A row inside 2 percent of that ratio is stored as terajoules (`unit_status = tj_checked`).

Electricity output is the exception, and it is detected from the numbers, not from a list of flow names. When the TJ column and the ktoe column hold the same figure, that figure is gigawatt-hours (France hydro in 2022 is about 45.5 TWh, and both columns read about 45,521). Those rows are multiplied by 3.6 (`unit_status = electricity_output_gwh`).

A row with both columns that matches neither rule is `suspect`. Its terajoule value is null and it is left out of the calculations. A TJ-only row is `tj_unchecked`. A ktoe-only row is multiplied by 41.868. A GWh row is multiplied by 3.6.

Markers `..`, `x`, `c`, and a blank value become null. The IEA flag is kept.

Each line of `WORLDBIG*.TXT` is one record: country, product, year, flow, unit, value. The file is not paired two lines at a time.

## Total final consumption

```
TFEC = TFC(TOTAL) − non-energy use(TOTAL)
```

Non-energy use is the `NONENUSE` / `NE_TOT` flow.

Traditional biomass is residential primary solid biofuels plus residential charcoal, and only for a country that is not on the OECD member list. For an OECD country that residential quantity is treated as modern. World and other aggregates are not given a special case: an aggregate code is not an OECD member, so its residential solid biofuels count as traditional. That overstates traditional biomass for `WLD` and similar rows.

```
s_RE = electricity output(renewables) / electricity output(total)
s_N  = electricity output(nuclear) / electricity output(total)
h_RE = heat output(renewables) / heat output(total)
h_N  = heat output(nuclear) / heat output(total)
```

Renewables and nuclear here are the balance memo products (`MRENEW` / `RENEWABLES_TOTAL`, and `NUCLEAR`).

## Electricity own-use multipliers

Reported generation is not the same as electricity that reaches final consumption. Each technology gets a multiplier from own-use and losses in the electricity balance:

```
base = |imports| + |exports| + |statistical difference| + |transformation|
loss share = |losses| / base
category share = |own-use flows in that category| / base
factor = −(conversion offset + category share + loss share)
multiplier = 1 − factor
```

Absolute values are used because the file often stores consumption as a negative number.

Conversion offsets: hydropower −0.01; nuclear, geothermal, and concentrating solar −0.06; other thermal (biopower) −0.07; solar PV, ocean, and wind 0. Own-use categories are fossil (mines, oil and gas, gas works, patent fuel, briquettes, refineries), nuclear industry, charcoal for biomass, pumped storage for hydro, and blast furnaces plus coke ovens for the residual “other” category. Plant own-use flows are recorded in the category table and are not added into these multipliers.

If `base` is zero, or any multiplier falls outside 0.5–1.5, the run uses the constants in `adjustment_factors.json` instead (hydropower 0.99, geothermal 0.94, solar PV 1.0, concentrating solar 0.94, ocean 1.0, wind 1.0, biopower 0.93, nuclear 0.94). `adjustment_used_fallback` is 1 in that case. Those constants are the documented fallback, not a second methodology.

Adjusted renewable electricity is the sum of each technology’s output, already in terajoules, times its multiplier, plus biopower (the sum of bioenergy electricity products times the biopower multiplier). The renewables memo total is not multiplied again on top of that sum.

## Economy

```
renewable TFEC = adjusted renewable electricity
                 + TFC(renewables)
                 + TFC(heat) × h_RE

nuclear TFEC   = adjusted nuclear electricity + TFC(heat) × h_N

fossil TFEC    = TFEC − nuclear TFEC − renewable TFEC

modern TFEC    = renewable TFEC − traditional biomass
```

Fossil is the residual, so renewable + nuclear + fossil equals TFEC by construction. `economy_*` repeats these totals.

Total energy supply is the `TES` flow, or `SUPPLY` if `TES` is absent. The fossil import ratio is fossil-product imports over that supply.

## Sectors

The six final-consumption sectors are residential, commercial and public, industry, transport, agriculture, and fishing. Each sector’s TFEC is

```
sector TFEC = sector total − (sector total / sum of sector totals) × non-energy use
```

This subtracts non-energy use even when the sector totals already exclude it. The gap shows up as `enduse_unallocated_tj`. It is the formula, not a validation error.

Buildings are residential plus commercial. Agriculture in the sector results includes fishing.

Industry and agriculture renewable energy is the sector’s renewables memo, plus district heat times `h_RE`, plus sector electricity times `s_RE`. Transport is different: biofuels in transport, plus transport electricity times `s_RE`. It does not use the transport renewables memo, which would double-count.

Renewable electricity used for heat is reported on its own and is not added into those sector renewable totals. Adding it would count the same electricity twice.

Industry subsectors (mining, paper, chemicals, food, iron and steel, non-ferrous, non-metallic minerals) use the subsector’s own total as the denominator, not the allocated industry TFEC.

## Renewable electricity for heat

Heat demand in a sector is district heat, plus solar thermal, plus geothermal, plus the non-negative remainder of the renewables memo after geothermal and solar thermal are removed. That demand is multiplied by an electricity-for-heat share and by the renewable share of final electricity (adjusted renewable electricity over TFC electricity, or `s_RE` if TFC electricity is zero).

Industry and agriculture use the industry share. Buildings (residential and commercial together) use the buildings share. Agriculture’s electricity-for-heat share is the industry figure.

The shares come from `heat_shares.json`. Lookup is the country, then the smallest matching region in `iea_heat_regions.json`, then World, then the defaults: industry and agriculture 0.04, buildings 0.11. A real (not forecast) row for a year at or before the requested year is preferred; otherwise the latest real row is used.

`bioenergy_shares.json` is the same kind of table for a solid-bioenergy assumption (country, then region, else 0.10). It is reported as `assumption_bioenergy_share`. It is not added into the TFEC identities above.

Of renewable district heat in buildings, a share `district_heating_bioenergy_share` (0.95 in `growth_parameters.json`) is reported as the bioenergy part. That is a split of heat already counted, not an extra quantity.

## Validation

`renweb validate` checks:

- `adjusted_tfec_tj` equals `raw_tfc_total_tj − raw_non_energy_use_tj` within 1e-6 relative. A miss is an error. The command exits 1 only when an error is present.
- Any `*_share` below −0.01 or above 1.15 is a warning.
- Fossil + nuclear + renewable economy shares should be near 1, with tolerance 0.15. The same three power-output shares use tolerance 0.10.
- A terajoule result below −1e-6 is a warning.
- A year-on-year change above 300 percent is a warning when the previous value is above 1 TJ.

At most 200 findings are returned.
