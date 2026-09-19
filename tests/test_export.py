from __future__ import annotations

from pathlib import Path

from renweb.compute.dag import compute
from renweb.export.writers import export_results
from renweb.ingest.pipeline import ingest
from renweb.ingest.txt import format_fixed_width
from renweb.validate.checks import validate


def test_compute_validate_export(con, tmp_path: Path) -> None:
    lines = [
        format_fixed_width("FRANCE", "TOTAL", 2022, "TFC", "TJ", 1000),
        format_fixed_width("FRANCE", "TOTAL", 2022, "TFC", "KTOE", 1000 / 41.868),
        format_fixed_width("FRANCE", "TOTAL", 2021, "TFC", "TJ", 100),
        format_fixed_width("FRANCE", "TOTAL", 2021, "TFC", "KTOE", 100 / 41.868),
        format_fixed_width("FRANCE", "MRENEW", 2022, "TFC", "TJ", 200),
        format_fixed_width("FRANCE", "MRENEW", 2022, "TFC", "KTOE", 200 / 41.868),
    ]
    path = tmp_path / "mini.txt"
    path.write_text("\n".join(lines) + "\n", encoding="latin-1")
    ingest(path, con)
    assert compute(con, countries=["FRA"]) == 2
    findings = validate(con)
    assert not any(item.severity == "error" for item in findings)
    # 100 to 1000 is a tenfold jump.
    assert any(item.check == "year_on_year" for item in findings)
    dest = tmp_path / "out"
    written = export_results(con, dest, ["parquet", "csv"])
    assert {path.suffix for path in written} == {".parquet", ".csv"}
    text = (dest / "results.csv").read_text(encoding="utf-8")
    assert "adjusted_tfec_tj" in text
    assert "FRA" in text
