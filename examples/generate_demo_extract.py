#!/usr/bin/env python3
"""Regenerate examples/worldbalances_demo.zip. See examples/README.md."""

from __future__ import annotations

import zipfile
from pathlib import Path

from renweb.demo_balances import build_lines


def main() -> None:
    root = Path(__file__).resolve().parent
    archive = root / "worldbalances_demo.zip"
    text = "\n".join(build_lines()) + "\n"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("WORLDBIG1.TXT", text.encode("latin-1"))
    raw_mb = len(text.encode("latin-1")) / (1024 * 1024)
    zip_mb = archive.stat().st_size / (1024 * 1024)
    print(
        f"Wrote {archive} ({zip_mb:.2f} MiB zip, {raw_mb:.2f} MiB txt, "
        f"{len(text.splitlines()):,} lines)"
    )


if __name__ == "__main__":
    main()
