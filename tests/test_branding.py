from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERN = re.compile(
    "|".join(
        [
            "REN" + "21",
            "ren" + "21",
            "RENWe" + "B",
            "Global Status " + "Report",
            r"\bGSR\b",
        ]
    )
)
SKIP = {".venv", "venv", "contrib", ".git", "__pycache__", ".pytest_cache", "dist"}


def test_published_tree_has_no_organisation_branding() -> None:
    hits: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP for part in path.parts):
            continue
        if path.suffix.lower() in {".png", ".xlsx", ".duckdb", ".parquet"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if PATTERN.search(text):
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []
