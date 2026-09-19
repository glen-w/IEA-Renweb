from __future__ import annotations

from pathlib import Path

import pytest

from renweb.warehouse import connect


@pytest.fixture
def con(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RENWEB_DATA", str(tmp_path / "renweb.duckdb"))
    database = connect()
    yield database
    database.close()
