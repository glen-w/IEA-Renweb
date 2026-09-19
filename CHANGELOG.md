# Changelog

## [1.0.0] - 2026-09-19

### Scope

This release covers IEA World Energy Balances processing with the following scope:

- **Included**: Renewable and fossil energy shares, sector splits (power, heat, transport, buildings, industry, agriculture)
- **Not included**: IEA extract is not redistributed (licensed data product); World Bank indicators, installed capacity data, and policy datasets are out of scope for this release

### Features

- Load IEA World Energy Balances (bulk TXT or SDMX CSV) into DuckDB
- Calculate total final energy consumption (TFEC)
- Compute renewable, fossil, and nuclear energy shares
- Calculate sector-level energy breakdowns
- Unit checking and validation (TJ/ktoe cross-check, electricity output GWh detection)
- Export results to CSV, Parquet, or Excel formats

### Data & Methodology

- **World aggregates and traditional biomass**: Applies OECD membership rule for traditional biomass classification
- **Unallocated energy**: `enduse_unallocated_tj` appears by design in the methodology (proportional non-energy use subtraction)
- **Heat and bioenergy defaults**: District heating and bioenergy shares are package assumptions, not IEA-published values
- **Edition**: Pinned to July 2026 IEA World Energy Balances extract edition

### Technical

- Added reference data files required for code crosswalk and country mapping
- Fixed package data inclusion in build configuration
- All CI checks passing (pytest, ruff, black, mypy)

[1.0.0]: https://github.com/glen-w/IEA-Renweb/releases/tag/v1.0.0
