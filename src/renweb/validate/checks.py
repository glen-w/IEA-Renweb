"""Result checks. Findings are warnings unless an identity is broken."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from renweb.compute.formulas import METHOD_VERSION

TFEC_TOLERANCE = 0.15
OTHER_TOLERANCE = 0.10
YOY_JUMP = 3.0
MAX_FINDINGS = 200


@dataclass(frozen=True)
class Finding:
    severity: str
    check: str
    message: str
    country: str | None = None
    year: int | None = None
    variable: str | None = None


def validate(con: Any) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(_identity(con))
    findings.extend(_share_bounds(con))
    findings.extend(
        _share_group(
            con,
            "tfec_shares",
            (
                "economy_share_fossil",
                "economy_share_nuclear",
                "economy_share_renewable",
            ),
            TFEC_TOLERANCE,
        )
    )
    findings.extend(
        _share_group(
            con,
            "electricity_output_shares",
            ("power_share_fossil", "power_share_nuclear", "power_share_renewable"),
            OTHER_TOLERANCE,
        )
    )
    findings.extend(_negative_energy(con))
    findings.extend(_year_on_year(con))
    if len(findings) > MAX_FINDINGS:
        extra = len(findings) - MAX_FINDINGS
        findings = findings[:MAX_FINDINGS]
        findings.append(
            Finding("warning", "truncated", f"{extra} further findings not shown")
        )
    return findings


def _identity(con: Any) -> list[Finding]:
    rows = con.execute(
        """
        SELECT country, year,
            max(CASE WHEN variable = 'adjusted_tfec_tj' THEN value END) AS tfec,
            max(CASE WHEN variable = 'raw_tfc_total_tj' THEN value END) AS tfc,
            max(CASE WHEN variable = 'raw_non_energy_use_tj' THEN value END) AS non_energy
        FROM results
        WHERE method_version = ?
        GROUP BY 1, 2
        """,
        [METHOD_VERSION],
    ).fetchall()
    found: list[Finding] = []
    for country, year, tfec, tfc, non_energy in rows:
        if tfec is None or tfc is None or non_energy is None:
            continue
        expected = tfc - non_energy
        scale = max(abs(expected), 1.0)
        if abs(tfec - expected) / scale > 1e-6:
            found.append(
                Finding(
                    "error",
                    "tfec_identity",
                    f"TFEC {tfec} != TFC {tfc} - non-energy use {non_energy}",
                    country,
                    int(year),
                    "adjusted_tfec_tj",
                )
            )
    return found


def _share_bounds(con: Any) -> list[Finding]:
    rows = con.execute(
        """
        SELECT country, year, variable, value
        FROM results
        WHERE method_version = ?
          AND variable LIKE '%\\_share' ESCAPE '\\'
          AND (value < -0.01 OR value > 1.15)
        """,
        [METHOD_VERSION],
    ).fetchall()
    return [
        Finding(
            "warning",
            "share_bounds",
            f"{variable} = {value:.4f} is outside -0.01 to 1.15",
            country,
            int(year),
            variable,
        )
        for country, year, variable, value in rows
    ]


def _share_group(
    con: Any, check: str, variables: tuple[str, ...], tolerance: float
) -> list[Finding]:
    cases = ", ".join(
        f"max(CASE WHEN variable = '{name}' THEN value END) AS v{index}"
        for index, name in enumerate(variables)
    )
    rows = con.execute(
        f"""
        SELECT country, year, {cases}
        FROM results
        WHERE method_version = ?
        GROUP BY 1, 2
        """,
        [METHOD_VERSION],
    ).fetchall()
    found: list[Finding] = []
    for row in rows:
        country, year, *parts = row
        if any(part is None for part in parts):
            continue
        total = sum(parts)
        if abs(total - 1.0) > tolerance:
            found.append(
                Finding(
                    "warning",
                    check,
                    f"shares sum to {total:.4f}, tolerance is {tolerance:.2f}",
                    country,
                    int(year),
                )
            )
    return found


def _negative_energy(con: Any) -> list[Finding]:
    rows = con.execute(
        """
        SELECT country, year, variable, value
        FROM results
        WHERE method_version = ? AND unit = 'TJ' AND value < -1e-6
        """,
        [METHOD_VERSION],
    ).fetchall()
    return [
        Finding(
            "warning",
            "non_negative",
            f"{variable} = {value}",
            country,
            int(year),
            variable,
        )
        for country, year, variable, value in rows
    ]


def _year_on_year(con: Any) -> list[Finding]:
    rows = con.execute(
        """
        SELECT country, variable, year, value, prev FROM (
            SELECT country, variable, year, value,
                lag(value) OVER (PARTITION BY country, variable ORDER BY year) AS prev
            FROM results
            WHERE method_version = ? AND variable LIKE '%\\_tj' ESCAPE '\\'
        )
        WHERE prev > 1 AND abs(value / prev - 1) > ?
        """,
        [METHOD_VERSION, YOY_JUMP],
    ).fetchall()
    return [
        Finding(
            "warning",
            "year_on_year",
            f"{variable} moved from {prev} to {value}",
            country,
            int(year),
            variable,
        )
        for country, variable, year, value, prev in rows
    ]
