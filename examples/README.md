# Example balances (synthetic)

`worldbalances_demo.zip` is a **small fixed-width extract** in the same shape as the IEA World Energy Balances bulk file. It is **not** licensed IEA data and must not be cited as such.

| Country label | Warehouse code | Role |
|---------------|----------------|------|
| EASTFENIA | EFN | Fictional |
| WESTMARSH | WMS | Fictional |
| NORTHALIA | NTH | Fictional |
| SOUTHAVIA | STH | Fictional |
| NIGERIA | NGA | Real label; **synthetic** values (scaled test frame) |
| FRANCE | FRA | Real label; **synthetic** values (scaled test frame) |

Each country has balances from 1960 through 2023 (~3 MiB uncompressed inside the zip). Values drift slowly by year so year-on-year checks behave realistically.

## Regenerate the zip

```bash
uv run python examples/generate_demo_extract.py
```

Commit the updated `worldbalances_demo.zip` if you change the generator.

## Try the CLI

```bash
export RENWEB_DATA=/tmp/renweb_demo.duckdb
uv run renweb ingest examples/worldbalances_demo.zip
uv run renweb compute
uv run renweb validate
uv run renweb export /tmp/renweb_demo_out --format csv
```

## Prove it in CI

```bash
uv run pytest tests/test_example_balances.py -q
```

That test ingests this zip, runs compute and validate, and checks a golden renewable share for Nigeria 2022.
