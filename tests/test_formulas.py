from __future__ import annotations

import pytest

from renweb.compute.formulas import Frame, adjustment_multipliers, compute_one


def _sample() -> dict[tuple[str, str], float]:
    return {
        ("TFC", "TOTAL"): 1000,
        ("NONENUSE", "TOTAL"): 100,
        ("TFC", "MRENEW"): 400,
        ("TFC", "ELECTR"): 200,
        ("TFC", "HEAT"): 50,
        ("ELOUTPUT", "TOTAL"): 100,
        ("ELOUTPUT", "MRENEW"): 40,
        ("ELOUTPUT", "HYDRO"): 30,
        ("ELOUTPUT", "NUCLEAR"): 10,
        ("ELOUTPUT", "WIND"): 10,
        ("HEATOUT", "TOTAL"): 20,
        ("HEATOUT", "MRENEW"): 10,
        ("RESIDENT", "TOTAL"): 300,
        ("RESIDENT", "PRIMSBIO"): 80,
        ("RESIDENT", "CHARCOAL"): 20,
        ("RESIDENT", "ELECTR"): 50,
        ("RESIDENT", "MRENEW"): 120,
        ("RESIDENT", "SOLARTH"): 10,
        ("RESIDENT", "GEOTHERM"): 5,
        ("RESIDENT", "HEAT"): 15,
        ("COMMPUB", "TOTAL"): 100,
        ("COMMPUB", "MRENEW"): 10,
        ("TOTIND", "TOTAL"): 250,
        ("TOTIND", "ELECTR"): 80,
        ("TOTIND", "MRENEW"): 40,
        ("TOTIND", "SOLARTH"): 5,
        ("TOTIND", "GEOTHERM"): 5,
        ("TOTIND", "HEAT"): 20,
        ("TOTTRANS", "TOTAL"): 200,
        ("TOTTRANS", "ELECTR"): 30,
        ("TOTTRANS", "BIODIESEL"): 25,
        ("AGRICULT", "TOTAL"): 40,
        ("FISHING", "TOTAL"): 10,
        ("TES", "TOTAL"): 1500,
        ("IMPORTS", "NATGAS"): 100,
        ("IMPORTS", "ELECTR"): 100,
        ("LOSSES", "ELECTR"): 10,
        ("PUMPSTOR", "ELECTR"): 5,
    }


def test_adjustment_multiplier_follows_the_own_use_identity() -> None:
    multipliers, fallback = adjustment_multipliers(Frame.from_pairs(_sample()))
    assert fallback is False
    # base = 100, losses share = 0.1, hydro own use = 0.05, hydro offset = -0.01
    assert multipliers["hydropower"] == pytest.approx(1.14)


def test_identities_and_transport() -> None:
    result = compute_one(Frame.from_pairs(_sample()), "NGA", 2022)
    tfec = result["adjusted_tfec_tj"][0]
    fossil = result["adjusted_tfec_fossil_tj"][0]
    nuclear = result["adjusted_tfec_nuclear_tj"][0]
    renewable = result["adjusted_tfec_renewable_tj"][0]
    assert tfec == pytest.approx(900)
    assert fossil + nuclear + renewable == pytest.approx(tfec)
    assert result["heatbio_traditional_biomass_tj"][0] == pytest.approx(100)
    transport_tfec = 200 - (200 / 900) * 100
    assert result["transport_tfec_tj"][0] == pytest.approx(transport_tfec)
    assert result["transport_renewable_tj"][0] == pytest.approx(25 + 30 * 0.4)
    assert 0 <= result["transport_renewable_share"][0] <= 1
    assert result["economy_fossil_import_ratio"][0] == pytest.approx(100 / 1500)


def test_heat_share_assumptions_are_not_results() -> None:
    result = compute_one(Frame.from_pairs(_sample()), "NGA", 2022)
    removed = {
        "assumption_elec_for_heat_industry",
        "assumption_elec_for_heat_buildings",
        "assumption_bioenergy_share",
        "renewable_electricity_heat_total_tj",
        "sectoral_electricity_for_heat_tj",
        "sectoral_electricity_excluding_heat_and_transport_tj",
        "buildings_district_heat_bioenergy_tj",
    }
    assert removed.isdisjoint(result)
    assert "buildings_district_heat_renewable_tj" in result
    assert "adjusted_tfec_traditional_biomass_tj" in result


def test_oecd_traditional_biomass_is_zero() -> None:
    result = compute_one(Frame.from_pairs(_sample()), "FRA", 2022)
    assert result["heatbio_traditional_biomass_tj"][0] == 0
    assert result["adjusted_tfec_modern_renewables_tj"][0] == pytest.approx(
        result["adjusted_tfec_renewable_tj"][0]
    )


def test_fallback_when_own_use_cannot_be_computed() -> None:
    frame = Frame.from_pairs({("TFC", "TOTAL"): 10, ("ELOUTPUT", "HYDRO"): 1})
    multipliers, fallback = adjustment_multipliers(frame)
    assert fallback is True
    assert multipliers["hydropower"] == pytest.approx(0.99)
    assert multipliers["wind"] == pytest.approx(1.0)
